import base64
from time import perf_counter
from typing import Any

import httpx

from app.providers.base import ProviderError
from app.repositories.history_repository import HistoryRepository
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.image_service import ImageService


class HistoryService:
    def __init__(
        self,
        repository: HistoryRepository,
        http_client: Any | None = None,
    ) -> None:
        self.repository = repository
        self.http_client = http_client

    async def generate(
        self,
        request: GenerateRequest,
        image_service: ImageService,
    ) -> GenerateResponse:
        history_id = await self.repository.create(
            kind="generate",
            prompt=request.prompt,
            provider=request.provider,
            model=request.model,
            detail=request.detail,
            image_count=request.count,
            size=request.size,
        )
        started_at = perf_counter()
        try:
            response = await image_service.generate(request)
            for position, image in enumerate(response.images):
                materialized = await self._materialize_image(image)
                if materialized is None:
                    continue
                mime_type, data = materialized
                extension = mime_type.split("/")[-1].replace("jpeg", "jpg")
                await self.repository.add_image(
                    history_id=history_id,
                    role="generated",
                    mime_type=mime_type,
                    filename=f"generated-{position + 1}.{extension}",
                    position=position,
                    data=data,
                )
            await self.repository.complete(
                history_id,
                elapsed_ms=max(1, round((perf_counter() - started_at) * 1000)),
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

    async def analyze(
        self,
        *,
        image_service: ImageService,
        provider: str,
        model: str,
        prompt: str,
        detail: str,
        image_bytes: bytes,
        content_type: str,
        filename: str | None,
    ) -> AnalyzeResponse:
        history_id = await self.repository.create(
            kind="analyze",
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
