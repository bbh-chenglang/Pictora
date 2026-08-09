import logging
import re
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any

from openai import APIError, APIStatusError, APITimeoutError, AsyncOpenAI
from pydantic import SecretStr

from app.observability import log_context
from app.providers.base import (
    ImageProvider,
    ProviderRequestError,
    ProviderTimeoutError,
    normalize_text,
)
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse

logger = logging.getLogger(__name__)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _image_results(response: Any) -> list[ImageResult]:
    choices = _value(response, "choices", []) or []
    if not choices:
        return []
    content = _value(_value(choices[0], "message", {}), "content", "")
    parts = content if isinstance(content, Sequence) and not isinstance(content, str) else [content]
    images: list[ImageResult] = []
    for part in parts:
        if isinstance(part, str):
            images.extend(ImageResult(url=url) for url in MARKDOWN_IMAGE_RE.findall(part))
            continue
        text = _value(part, "text")
        if isinstance(text, str):
            images.extend(ImageResult(url=url) for url in MARKDOWN_IMAGE_RE.findall(text))
        image_url = _value(part, "image_url")
        url = _value(image_url, "url") if image_url is not None else None
        if isinstance(url, str) and url:
            if url.startswith("data:"):
                images.append(ImageResult(base64_data=url))
            else:
                images.append(ImageResult(url=url))
    return images


class GeminiProvider(ImageProvider):
    provider_id = "gemini"
    label = "Gemini"

    def __init__(
        self,
        api_key: SecretStr | str,
        base_url: str,
        model: str,
        client: Any | None = None,
    ) -> None:
        secret = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self.model = model
        self.client = client or AsyncOpenAI(api_key=secret, base_url=base_url)

    async def generate_image(self, request: GenerateRequest) -> GenerateResponse:
        started_at = perf_counter()
        try:
            response = await self.client.chat.completions.create(
                model=request.model,
                messages=[{"role": "user", "content": request.prompt}],
            )
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
        images = _image_results(response)
        logger.info(
            "image_generation step=provider_api_completed duration_ms=%d provider=%s model=%s image_count=%d %s",
            max(1, round((perf_counter() - started_at) * 1000)),
            self.provider_id,
            request.model,
            len(images),
            " ".join(f"{key}={value}" for key, value in log_context().items()),
        )
        return GenerateResponse(provider=self.provider_id, model=request.model, images=images)

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> AnalyzeResponse:
        from app.providers.openai_provider import OpenAIProvider

        return await OpenAIProvider(
            api_key="", base_url="", model=model, client=self.client
        ).analyze_image(model, prompt, image_bytes, content_type)
