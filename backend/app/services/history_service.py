import asyncio
import base64
import ipaddress
import logging
import socket
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from app.observability import generation_id, log_context
from app.providers.base import ProviderError
from app.repositories.history_repository import (
    GenerationTaskNotRunnableError,
    HistoryRepository,
)
from app.repositories.project_repository import ProjectNotFoundError, ProjectRepository
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import (
    GenerateRequest,
    GenerateResponse,
    ReferenceImage,
    ReferenceImageInput,
    normalize_reference_images,
)
from app.services.image_service import ImageService


logger = logging.getLogger(__name__)
MAX_REMOTE_IMAGE_BYTES = 20 * 1024 * 1024
REMOTE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


async def _resolve_host(hostname: str, port: int) -> list[str]:
    records = await asyncio.to_thread(
        socket.getaddrinfo,
        hostname,
        port,
        type=socket.SOCK_STREAM,
    )
    return sorted({record[4][0] for record in records})


def _detected_image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _image_type_diagnostic(
    declared_type: str,
    detected_type: str | None,
    data: bytes,
) -> str:
    return (
        "Provider base64 image has an invalid image type "
        f"(declared={declared_type} detected={detected_type or 'unknown'} "
        f"bytes={len(data)} signature={data[:12].hex()})"
    )


def _duration_ms(started_at: float) -> int:
    return max(1, round((perf_counter() - started_at) * 1000))


def _log_step(step: str, started_at: float, **fields: object) -> None:
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    context = log_context()
    context_text = " ".join(f"{key}={value}" for key, value in context.items())
    suffix = " ".join(part for part in (context_text, details) if part)
    logger.info("image_generation step=%s duration_ms=%d %s", step, _duration_ms(started_at), suffix)


class HistoryService:
    def __init__(
        self,
        repository: HistoryRepository,
        http_client: Any | None = None,
        project_repository: ProjectRepository | None = None,
        host_resolver: Any | None = None,
    ) -> None:
        self.repository = repository
        self.http_client = http_client
        self.project_repository = project_repository or ProjectRepository(repository.database_path)
        self.host_resolver = host_resolver or _resolve_host

    async def _resolve_project(self, project_id: int | None, user_id: int) -> int:
        if project_id is not None:
            if await self.project_repository.get_owned(project_id, user_id) is None:
                raise ProjectNotFoundError(project_id)
            return project_id
        projects = await self.project_repository.list_with_history(user_id)
        if not projects:
            raise ProjectNotFoundError(user_id)
        return projects[0].id

    async def generate(
        self,
        request: GenerateRequest,
        image_service: ImageService,
        user_id: int = 1,
        reference_image: ReferenceImageInput | None = None,
    ) -> GenerateResponse:
        history_id = await self.create_generation(
            request,
            user_id,
            reference_image=reference_image,
        )
        return await self.execute_generation(
            history_id,
            request,
            image_service,
            user_id,
            reference_image=reference_image,
        )

    async def create_generation(
        self,
        request: GenerateRequest,
        user_id: int = 1,
        reference_image: ReferenceImageInput | None = None,
        *,
        include_batch_id: bool = False,
        include_task_id: bool = False,
    ) -> int | tuple[int, int]:
        project_id = await self._resolve_project(request.project_id, user_id)
        stored_size = request.aspect_ratio or request.size
        expected_image_count = ImageService.expected_image_count(request)
        if request.conversation_id is None:
            history_id = await self.repository.create(
                user_id=user_id,
                kind="generate",
                project_id=project_id,
                prompt=request.prompt,
                provider=request.provider,
                model=request.model,
                detail=request.detail,
                image_count=expected_image_count,
                api_key_config_id=request.api_key_config_id,
                size=stored_size,
                resolution=request.resolution,
                output_format=request.output_format,
                background=request.background,
                output_compression=request.output_compression,
                moderation=request.moderation,
                views=request.views,
            )
            batch_id = await self.repository.latest_generation_batch_id(
                user_id=user_id,
                history_id=history_id,
            )
        else:
            history_id = request.conversation_id
            batch_id = await self.repository.restart_generation(
                history_id,
                user_id=user_id,
                project_id=project_id,
                prompt=request.prompt,
                provider=request.provider,
                model=request.model,
                detail=request.detail,
                image_count=expected_image_count,
                api_key_config_id=request.api_key_config_id,
                size=stored_size,
                resolution=request.resolution,
                output_format=request.output_format,
                background=request.background,
                output_compression=request.output_compression,
                moderation=request.moderation,
                views=request.views,
            )
        try:
            images = normalize_reference_images(reference_image)
            await self.repository.add_reference_images(
                history_id=history_id,
                user_id=user_id,
                batch_id=batch_id,
                images=[
                    (image.content_type, image.filename, image.data, image.category)
                    for image in images
                ],
            )
        except Exception:
            await self.repository.fail_generation_batch(
                history_id,
                batch_id,
                error_code="internal_error",
                error_message="参考图保存失败",
            )
            raise
        task_id = await self.repository.create_generation_task(
            user_id=user_id,
            history_id=history_id,
            batch_id=batch_id,
        ) if include_task_id else None
        if include_task_id:
            return history_id, batch_id, task_id
        return (history_id, batch_id) if include_batch_id else history_id

    async def execute_generation(
        self,
        history_id: int,
        request: GenerateRequest,
        image_service: ImageService,
        user_id: int = 1,
        reference_image: ReferenceImageInput | None = None,
        *,
        batch_id: int | None = None,
        task_id: int | None = None,
        worker_id: str | None = None,
    ) -> GenerateResponse:
        generation_token = generation_id.set(uuid4().hex)
        started_at = perf_counter()
        heartbeat_task: asyncio.Task[None] | None = None
        logger.info(
            "image_generation step=generation_started duration_ms=0 generation_id=%s provider=%s model=%s "
            "requested_count=%d aspect_ratio=%s requested_resolution=%s history_id=%d",
            generation_id.get(),
            request.provider,
            request.model,
            request.count,
            request.aspect_ratio or "legacy",
            request.resolution or "legacy",
            history_id,
        )
        try:
            if task_id is not None:
                if not worker_id:
                    raise ValueError("worker_id is required when executing a generation task")
                claimed = await self.repository.mark_generation_task_running(
                    task_id,
                    user_id,
                    worker_id=worker_id,
                )
                if not claimed:
                    raise GenerationTaskNotRunnableError(task_id)
                heartbeat_task = asyncio.create_task(
                    self._heartbeat_generation_task(
                        task_id,
                        user_id,
                        worker_id,
                        asyncio.current_task(),
                    ),
                    name=f"image-generation-heartbeat-{task_id}",
                )
            else:
                heartbeat_task = None
            if batch_id is None:
                batch_id = await self.repository.latest_generation_batch_id(
                    user_id=user_id,
                    history_id=history_id,
                )
            generated_position = await self.repository.next_image_position(
                user_id=user_id,
                history_id=history_id,
                role="generated",
            )
            processed_positions: set[int] = set()
            stored_image_count = 0
            persist_lock = asyncio.Lock()

            async def persist_generated_image_locked(image: ImageResult) -> None:
                nonlocal stored_image_count
                batch_position = (
                    image.generation_position
                    if image.generation_position is not None
                    else len(processed_positions)
                )
                if batch_position in processed_positions:
                    return
                processed_positions.add(batch_position)
                materialize_started_at = perf_counter()
                materialized = await self._materialize_image(image)
                _log_step(
                    "image_materialize_completed",
                    materialize_started_at,
                    history_id=history_id,
                    image_index=batch_position,
                    source="base64" if image.base64_data else "url" if image.url else "none",
                    byte_count=len(materialized[1]) if materialized else 0,
                )
                if materialized is None:
                    return
                mime_type, data = materialized
                extension = mime_type.split("/")[-1].replace("jpeg", "jpg")
                save_started_at = perf_counter()
                image_id = await self.repository.add_image(
                    history_id=history_id,
                    user_id=user_id,
                    role="generated",
                    mime_type=mime_type,
                    filename=f"generated-{generated_position + stored_image_count + 1}.{extension}",
                    position=generated_position + stored_image_count,
                    batch_position=batch_position,
                    data=data,
                    batch_id=batch_id,
                    task_id=task_id,
                    worker_id=worker_id,
                )
                if image_id is not None:
                    stored_image_count += 1
                _log_step(
                    "history_image_saved",
                    save_started_at,
                    history_id=history_id,
                    image_index=batch_position,
                    byte_count=len(data),
                )

            async def persist_generated_image(image: ImageResult) -> None:
                async with persist_lock:
                    await persist_generated_image_locked(image)

            async def should_skip_generation_slot(position: int) -> bool:
                return await self.repository.generation_slot_is_unavailable(
                    user_id,
                    history_id,
                    batch_id,
                    position,
                )

            image_service_started_at = perf_counter()
            response = (
                await image_service.generate(
                    request,
                    reference_image,
                    on_image=persist_generated_image,
                    should_skip=should_skip_generation_slot,
                )
                if reference_image is not None
                else await image_service.generate(
                    request,
                    on_image=persist_generated_image,
                    should_skip=should_skip_generation_slot,
                )
            )
            _log_step(
                "image_service_completed",
                image_service_started_at,
                history_id=history_id,
                image_count=len(response.images),
            )
            if task_id is not None and not await self.repository.generation_task_is_active(
                task_id,
                user_id,
                worker_id=worker_id,
            ):
                raise GenerationTaskNotRunnableError(task_id)
            for image in response.images:
                await persist_generated_image(image)
            complete_started_at = perf_counter()
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
                heartbeat_task = None
            completed = await self.repository.complete_generation_batch(
                history_id,
                batch_id,
                elapsed_ms=_duration_ms(started_at),
                task_id=task_id,
                user_id=user_id,
                worker_id=worker_id,
                failure_details=self._generation_failure_details(response),
            )
            if not completed:
                raise GenerationTaskNotRunnableError(task_id or history_id)
            project_id = await self.repository.get_project_id(user_id, history_id)
            if project_id is not None:
                await self.project_repository.rename_if_empty(
                    project_id,
                    user_id,
                    request.prompt[:5],
                )
            _log_step("history_completed", complete_started_at, history_id=history_id)
            _log_step(
                "generation_completed",
                started_at,
                history_id=history_id,
                image_count=len(response.images),
            )
            return response
        except asyncio.CancelledError:
            _log_step("generation_cancelled", started_at, history_id=history_id)
            if batch_id is None:
                batch_id = await self.repository.latest_generation_batch_id(
                    user_id=user_id,
                    history_id=history_id,
                )
            await self.repository.fail_generation_batch(
                history_id,
                batch_id,
                error_code="generation_cancelled",
                error_message="生成任务已取消",
                task_id=task_id,
                user_id=user_id,
                worker_id=worker_id,
                task_status="cancelled",
            )
            raise
        except GenerationTaskNotRunnableError:
            raise
        except ProviderError as exc:
            _log_step("generation_failed", started_at, history_id=history_id, error_code=exc.code)
            if batch_id is None:
                batch_id = await self.repository.latest_generation_batch_id(
                    user_id=user_id,
                    history_id=history_id,
                )
            await self.repository.fail_generation_batch(
                history_id,
                batch_id,
                error_code=exc.code,
                error_message=exc.message,
                task_id=task_id,
                user_id=user_id,
                worker_id=worker_id,
            )
            raise
        except Exception as exc:
            diagnostic = f"任务处理失败（{type(exc).__name__}）"
            detail = " ".join(str(exc).split())[:240]
            if detail:
                diagnostic = f"{diagnostic}: {detail}"
            logger.exception(
                "image_generation step=generation_exception history_id=%d exception_type=%s exception=%s",
                history_id,
                type(exc).__name__,
                str(exc),
            )
            _log_step("generation_failed", started_at, history_id=history_id, error_code="internal_error")
            if batch_id is None:
                batch_id = await self.repository.latest_generation_batch_id(
                    user_id=user_id,
                    history_id=history_id,
                )
            await self.repository.fail_generation_batch(
                history_id,
                batch_id,
                error_code="internal_error",
                error_message=diagnostic,
                task_id=task_id,
                user_id=user_id,
                worker_id=worker_id,
            )
            raise
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
            generation_id.reset(generation_token)

    @staticmethod
    def _generation_failure_details(response: GenerateResponse) -> str | None:
        messages = list(dict.fromkeys(
            failure.error_message.strip()
            for failure in response.failures
            if failure.error_message.strip()
        ))
        if not messages:
            return None
        details = "；".join(messages[:3])
        if len(messages) > 3:
            details += f"；另有 {len(messages) - 3} 种错误"
        return details[:800]

    async def _heartbeat_generation_task(
        self,
        task_id: int,
        user_id: int,
        worker_id: str,
        owner_task: asyncio.Task[Any] | None,
    ) -> None:
        while True:
            await asyncio.sleep(15)
            renewed = await self.repository.heartbeat_generation_task(
                task_id,
                user_id,
                worker_id=worker_id,
            )
            if not renewed:
                if owner_task is not None:
                    owner_task.cancel()
                return

    async def cancel_generation(self, history_id: int) -> None:
        await self.repository.fail(
            history_id,
            error_code="generation_cancelled",
            error_message="生成任务已取消",
        )

    async def analyze(
        self,
        *,
        user_id: int,
        project_id: int | None = None,
        image_service: ImageService,
        provider: str,
        model: str,
        api_key_config_id: int | None = None,
        prompt: str,
        detail: str,
        image_bytes: bytes,
        content_type: str,
        filename: str | None,
        reference_images: ReferenceImageInput | None = None,
    ) -> AnalyzeResponse:
        project_id = await self._resolve_project(project_id, user_id)
        history_id = await self.repository.create(
            user_id=user_id, kind="analyze",
            project_id=project_id,
            prompt=prompt,
            provider=provider,
            model=model,
            detail=detail,
            image_count=1,
            api_key_config_id=api_key_config_id,
            size=None,
        )
        batch_id = await self.repository.latest_generation_batch_id(
            user_id=user_id,
            history_id=history_id,
        )
        started_at = perf_counter()
        try:
            images = normalize_reference_images(reference_images) or [
                ReferenceImage(
                    data=image_bytes,
                    content_type=content_type,
                    filename=filename,
                )
            ]
            await self.repository.add_reference_images(
                history_id=history_id,
                user_id=user_id,
                batch_id=batch_id,
                images=[
                    (image.content_type, image.filename, image.data, image.category)
                    for image in images
                ],
            )
            analyze_args = (
                provider,
                model,
                prompt,
                detail,
                image_bytes,
                content_type,
            )
            if api_key_config_id is None:
                response = await image_service.analyze(
                    *analyze_args,
                    **({"reference_images": images} if len(images) > 1 else {}),
                )
            else:
                response = await image_service.analyze(
                    *analyze_args,
                    api_key_config_id=api_key_config_id,
                    **({"reference_images": images} if len(images) > 1 else {}),
                )
            await self.repository.complete(
                history_id,
                elapsed_ms=max(1, round((perf_counter() - started_at) * 1000)),
                analysis_text=response.text,
            )
            return response
        except ProviderError as exc:
            await self.repository.fail_generation_batch(
                history_id,
                batch_id,
                error_code=exc.code,
                error_message=exc.message,
            )
            raise
        except Exception:
            await self.repository.fail_generation_batch(
                history_id,
                batch_id,
                error_code="internal_error",
                error_message="任务处理失败",
            )
            raise

    async def _materialize_image(
        self,
        image: ImageResult,
    ) -> tuple[str, bytes] | None:
        if image.base64_data:
            source = image.base64_data.strip()
            mime_type = (
                image.mime_type.strip().lower()
                if image.mime_type and image.mime_type.strip().lower().startswith("image/")
                else "image/png"
            )
            encoded = source
            if source.startswith("data:") and "," in source:
                metadata, encoded = source.split(",", 1)
                declared_type = metadata[5:].split(";", 1)[0].strip().lower()
                if declared_type.startswith("image/"):
                    mime_type = declared_type
            padding = len(encoded) - len(encoded.rstrip("="))
            estimated_size = max(0, (len(encoded) * 3) // 4 - padding)
            if estimated_size > MAX_REMOTE_IMAGE_BYTES:
                raise ValueError("Provider image exceeds the 20 MB limit")
            content = base64.b64decode(encoded, validate=True)
            if len(content) > MAX_REMOTE_IMAGE_BYTES:
                raise ValueError("Provider image exceeds the 20 MB limit")
            if mime_type == "image/jpg":
                mime_type = "image/jpeg"
            detected_type = _detected_image_type(content)
            if detected_type not in REMOTE_IMAGE_TYPES:
                diagnostic = _image_type_diagnostic(mime_type, detected_type, content)
                logger.warning(
                    "image_generation step=base64_image_type_invalid "
                    "declared_type=%s detected_type=%s byte_count=%d signature_hex=%s",
                    mime_type,
                    detected_type or "unknown",
                    len(content),
                    content[:12].hex(),
                )
                raise ValueError(diagnostic)
            if detected_type != mime_type:
                logger.warning(
                    "image_generation step=base64_image_type_normalized "
                    "declared_type=%s detected_type=%s byte_count=%d signature_hex=%s",
                    mime_type,
                    detected_type,
                    len(content),
                    content[:12].hex(),
                )
            return detected_type, content
        if not image.url:
            return None

        parsed = urlsplit(image.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Provider image URL must be a public HTTPS URL")
        addresses = await self.host_resolver(parsed.hostname, parsed.port or 443)
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError("Provider image URL resolves to a non-public address")

        if self.http_client is not None:
            response = await self.http_client.get(image.url)
            if 300 <= response.status_code < 400:
                raise ValueError("Provider image redirects are not allowed")
            response.raise_for_status()
            declared_length = response.headers.get("Content-Length")
            if declared_length and int(declared_length) > MAX_REMOTE_IMAGE_BYTES:
                raise ValueError("Provider image exceeds the 20 MB limit")
            content = response.content
        else:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                async with client.stream("GET", image.url) as response:
                    if 300 <= response.status_code < 400:
                        raise ValueError("Provider image redirects are not allowed")
                    response.raise_for_status()
                    declared_length = response.headers.get("Content-Length")
                    if declared_length and int(declared_length) > MAX_REMOTE_IMAGE_BYTES:
                        raise ValueError("Provider image exceeds the 20 MB limit")
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        chunks.extend(chunk)
                        if len(chunks) > MAX_REMOTE_IMAGE_BYTES:
                            raise ValueError("Provider image exceeds the 20 MB limit")
                    content = bytes(chunks)
        if len(content) > MAX_REMOTE_IMAGE_BYTES:
            raise ValueError("Provider image exceeds the 20 MB limit")
        declared_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if declared_type == "image/jpg":
            declared_type = "image/jpeg"
        detected_type = _detected_image_type(content)
        if declared_type not in REMOTE_IMAGE_TYPES or detected_type != declared_type:
            raise ValueError("Provider image response has an invalid image type")
        return detected_type, content
