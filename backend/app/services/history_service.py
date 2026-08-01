import base64
import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

from app.observability import generation_id, log_context
from app.providers.base import ProviderError
from app.repositories.history_repository import HistoryRepository
from app.repositories.project_repository import ProjectNotFoundError, ProjectRepository
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.image_service import ImageService


logger = logging.getLogger(__name__)


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
    ) -> None:
        self.repository = repository
        self.http_client = http_client
        self.project_repository = project_repository or ProjectRepository(repository.database_path)

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
    ) -> GenerateResponse:
        generation_token = generation_id.set(uuid4().hex)
        started_at = perf_counter()
        logger.info(
            "image_generation step=generation_started duration_ms=0 generation_id=%s provider=%s model=%s requested_count=%d",
            generation_id.get(),
            request.provider,
            request.model,
            request.count,
        )
        create_started_at = perf_counter()
        project_id = await self._resolve_project(request.project_id, user_id)
        history_id = await self.repository.create(
            user_id=user_id, kind="generate",
            project_id=project_id,
            prompt=request.prompt,
            provider=request.provider,
            model=request.model,
            detail=request.detail,
            image_count=request.count,
            size=request.size,
        )
        _log_step("history_created", create_started_at, history_id=history_id)
        try:
            image_service_started_at = perf_counter()
            response = await image_service.generate(request)
            _log_step(
                "image_service_completed",
                image_service_started_at,
                history_id=history_id,
                image_count=len(response.images),
            )
            for position, image in enumerate(response.images):
                materialize_started_at = perf_counter()
                materialized = await self._materialize_image(image)
                _log_step(
                    "image_materialize_completed",
                    materialize_started_at,
                    history_id=history_id,
                    image_index=position,
                    source="base64" if image.base64_data else "url" if image.url else "none",
                    byte_count=len(materialized[1]) if materialized else 0,
                )
                if materialized is None:
                    continue
                mime_type, data = materialized
                extension = mime_type.split("/")[-1].replace("jpeg", "jpg")
                save_started_at = perf_counter()
                await self.repository.add_image(
                    history_id=history_id,
                    user_id=user_id,
                    role="generated",
                    mime_type=mime_type,
                    filename=f"generated-{position + 1}.{extension}",
                    position=position,
                    data=data,
                )
                _log_step(
                    "history_image_saved",
                    save_started_at,
                    history_id=history_id,
                    image_index=position,
                    byte_count=len(data),
                )
            complete_started_at = perf_counter()
            await self.repository.complete(
                history_id,
                elapsed_ms=_duration_ms(started_at),
            )
            _log_step("history_completed", complete_started_at, history_id=history_id)
            _log_step(
                "generation_completed",
                started_at,
                history_id=history_id,
                image_count=len(response.images),
            )
            return response
        except ProviderError as exc:
            _log_step("generation_failed", started_at, history_id=history_id, error_code=exc.code)
            await self.repository.fail(
                history_id,
                error_code=exc.code,
                error_message=exc.message,
            )
            raise
        except Exception:
            _log_step("generation_failed", started_at, history_id=history_id, error_code="internal_error")
            await self.repository.fail(
                history_id,
                error_code="internal_error",
                error_message="任务处理失败",
            )
            raise
        finally:
            generation_id.reset(generation_token)

    async def analyze(
        self,
        *,
        user_id: int,
        project_id: int | None = None,
        image_service: ImageService,
        provider: str,
        model: str,
        prompt: str,
        detail: str,
        image_bytes: bytes,
        content_type: str,
        filename: str | None,
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
            size=None,
        )
        started_at = perf_counter()
        try:
            await self.repository.add_image(
                history_id=history_id,
                user_id=user_id,
                role="reference",
                mime_type=content_type,
                filename=filename,
                position=0,
                data=image_bytes,
            )
            response = await image_service.analyze(
                provider,
                model,
                prompt,
                detail,
                image_bytes,
                content_type,
            )
            await self.repository.complete(
                history_id,
                elapsed_ms=max(1, round((perf_counter() - started_at) * 1000)),
                analysis_text=response.text,
            )
            return response
        except ProviderError as exc:
            await self.repository.fail(
                history_id,
                error_code=exc.code,
                error_message=exc.message,
            )
            raise
        except Exception:
            await self.repository.fail(
                history_id,
                error_code="internal_error",
                error_message="任务处理失败",
            )
            raise

    async def _materialize_image(
        self,
        image: ImageResult,
    ) -> tuple[str, bytes] | None:
        if image.base64_data:
            encoded = image.base64_data.split(",", 1)[-1]
            return "image/png", base64.b64decode(encoded, validate=True)
        if not image.url:
            return None

        if self.http_client is not None:
            response = await self.http_client.get(image.url)
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(image.url)
        response.raise_for_status()
        mime_type = response.headers.get("Content-Type", "image/png")
        return mime_type.split(";", 1)[0].strip(), response.content
