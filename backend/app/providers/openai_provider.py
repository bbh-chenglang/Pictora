import logging
from io import BytesIO
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any

from openai import (
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)
from pydantic import SecretStr

from app.observability import log_context
from app.schemas.analyze import AnalyzeResponse
from app.providers.base import (
    ImageProvider,
    ProviderRequestError,
    ProviderTimeoutError,
    image_data_url,
    normalize_image_results,
    normalize_text,
    parse_retry_after,
)
from app.schemas.generate import (
    GenerateRequest,
    GenerateResponse,
    ReferenceImage,
    ReferenceImageInput,
    normalize_reference_images,
)


logger = logging.getLogger(__name__)


class OpenAIProvider(ImageProvider):
    provider_id = "openai"
    label = "OpenAI"

    def __init__(
        self,
        api_key: SecretStr | str,
        base_url: str,
        model: str,
        client: Any | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        secret = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self.model = model
        self.client = (
            client
            if client is not None
            else AsyncOpenAI(
                api_key=secret,
                base_url=base_url,
                default_headers=default_headers,
            )
        )

    async def generate_image(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImageInput | None = None,
    ) -> GenerateResponse:
        output_size = request.size or "auto"
        arguments: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "n": getattr(request, "count", 1),
            "size": output_size,
        }
        if request.detail in {"auto", "low", "medium", "high"}:
            arguments["quality"] = request.detail
        output_format = getattr(request, "output_format", None)
        if output_format:
            arguments["output_format"] = output_format
        background = getattr(request, "background", None)
        if background:
            arguments["background"] = background
        output_compression = getattr(request, "output_compression", None)
        if output_compression is not None and output_format in {"jpeg", "webp"}:
            arguments["output_compression"] = output_compression
        moderation = getattr(request, "moderation", None)
        if moderation:
            arguments["moderation"] = moderation
        started_at = perf_counter()
        context = " ".join(f"{key}={value}" for key, value in log_context().items())
        logger.info(
            "image_generation step=provider_api_started provider=%s model=%s requested_resolution=%s size=%s %s",
            self.provider_id,
            request.model,
            getattr(request, "resolution", None) or "legacy",
            output_size,
            context,
        )
        try:
            reference_images = normalize_reference_images(reference_image)
            if not reference_images:
                response = await self.client.images.generate(**arguments)
            else:
                image_files = []
                for index, image in enumerate(reference_images):
                    image_file = BytesIO(image.data)
                    image_file.name = image.filename or f"reference-image-{index + 1}"
                    image_files.append(image_file)
                edit_arguments = dict(arguments)
                edit_arguments.pop("moderation", None)
                response = await self.client.images.edit(
                    image=image_files[0] if len(image_files) == 1 else image_files,
                    **edit_arguments,
                )
        except APIStatusError as exc:
            self._log_generation_failure(request, started_at, "api_status_error")
            raise ProviderRequestError(
                status_code=exc.status_code,
                response_content=exc.response.content,
                content_type=exc.response.headers.get("content-type"),
                retry_after_seconds=parse_retry_after(
                    exc.response.headers.get("retry-after")
                ),
            ) from None
        except APITimeoutError:
            self._log_generation_failure(request, started_at, "timeout")
            raise ProviderTimeoutError() from None
        except APIError:
            self._log_generation_failure(request, started_at, "api_error")
            raise ProviderRequestError() from None
        images = normalize_image_results(response)
        if output_format:
            mime_type = f"image/{output_format}"
            images = [
                image if image.mime_type else image.model_copy(update={"mime_type": mime_type})
                for image in images
            ]
        logger.info(
            "image_generation step=provider_api_completed duration_ms=%d provider=%s model=%s image_count=%d %s",
            max(1, round((perf_counter() - started_at) * 1000)),
            self.provider_id,
            request.model,
            len(images),
            context,
        )
        return GenerateResponse(provider=self.provider_id, model=request.model, images=images)

    def _log_generation_failure(
        self,
        request: GenerateRequest,
        started_at: float,
        error_type: str,
        *,
        status_code: int | None = None,
        upstream_message: str | None = None,
    ) -> None:
        logger.error(
            "image_generation step=provider_api_failed duration_ms=%d provider=%s model=%s "
            "error_type=%s status_code=%s upstream_message=%s %s",
            max(1, round((perf_counter() - started_at) * 1000)),
            self.provider_id,
            request.model,
            error_type,
            status_code if status_code is not None else "none",
            upstream_message or "none",
            " ".join(f"{key}={value}" for key, value in log_context().items()),
        )

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> AnalyzeResponse:
        return await self.analyze_images(
            model,
            prompt,
            [ReferenceImage(data=image_bytes, content_type=content_type)],
        )

    async def analyze_images(
        self,
        model: str,
        prompt: str,
        reference_images: Sequence[ReferenceImage],
    ) -> AnalyzeResponse:
        arguments = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        *[
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url(image.data, image.content_type)
                                },
                            }
                            for image in reference_images
                        ],
                    ],
                }
            ],
        }
        try:
            response = await self.client.chat.completions.create(**arguments)
        except APIStatusError as exc:
            raise ProviderRequestError(
                status_code=exc.status_code,
                response_content=exc.response.content,
                content_type=exc.response.headers.get("content-type"),
                retry_after_seconds=parse_retry_after(
                    exc.response.headers.get("retry-after")
                ),
            ) from None
        except APITimeoutError:
            raise ProviderTimeoutError() from None
        except APIError:
            raise ProviderRequestError() from None
        return AnalyzeResponse(provider=self.provider_id, model=model, text=normalize_text(response))
