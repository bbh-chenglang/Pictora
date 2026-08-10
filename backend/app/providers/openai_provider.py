import logging
from io import BytesIO
from collections.abc import Mapping
from time import perf_counter
from typing import Any

from openai import (
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
)
from pydantic import SecretStr

from app.image_dimensions import output_size
from app.observability import log_context
from app.schemas.analyze import AnalyzeResponse
from app.providers.base import (
    ImageProvider,
    ProviderRequestError,
    ProviderTimeoutError,
    image_data_url,
    normalize_image_results,
    normalize_text,
)
from app.schemas.generate import GenerateRequest, GenerateResponse, ReferenceImage


logger = logging.getLogger(__name__)


def _output_size(request: GenerateRequest) -> str:
    return output_size(
        getattr(request, "aspect_ratio", None),
        getattr(request, "resolution", None),
        request.size,
    )


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
        reference_image: ReferenceImage | None = None,
    ) -> GenerateResponse:
        output_size = _output_size(request)
        arguments: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "size": output_size,
        }
        if request.detail in {"low", "medium", "high"}:
            arguments["quality"] = request.detail
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
            if reference_image is None:
                response = await self.client.images.generate(**arguments)
            else:
                image_file = BytesIO(reference_image.data)
                image_file.name = reference_image.filename or "reference-image"
                response = await self.client.images.edit(image=image_file, **arguments)
        except APIStatusError as exc:
            self._log_generation_failure(request, started_at, "api_status_error")
            raise ProviderRequestError(
                status_code=exc.status_code,
                response_content=exc.response.content,
                content_type=exc.response.headers.get("content-type"),
            ) from None
        except APITimeoutError:
            self._log_generation_failure(request, started_at, "timeout")
            raise ProviderTimeoutError() from None
        except APIError:
            self._log_generation_failure(request, started_at, "api_error")
            raise ProviderRequestError() from None
        images = normalize_image_results(response)
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
    ) -> None:
        logger.error(
            "image_generation step=provider_api_failed duration_ms=%d provider=%s model=%s error_type=%s %s",
            max(1, round((perf_counter() - started_at) * 1000)),
            self.provider_id,
            request.model,
            error_type,
            " ".join(f"{key}={value}" for key, value in log_context().items()),
        )

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> AnalyzeResponse:
        arguments = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_data_url(image_bytes, content_type)},
                        },
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
            ) from None
        except APITimeoutError:
            raise ProviderTimeoutError() from None
        except APIError:
            raise ProviderRequestError() from None
        return AnalyzeResponse(provider=self.provider_id, model=model, text=normalize_text(response))
