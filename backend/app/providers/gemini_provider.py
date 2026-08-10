import base64
import logging
from collections.abc import Mapping, Sequence
from time import perf_counter
from typing import Any
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.observability import log_context
from app.providers.compatible_provider import COMPATIBLE_USER_AGENT
from app.providers.base import (
    ImageProvider,
    ProviderRequestError,
    ProviderTimeoutError,
)
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse, ReferenceImage


logger = logging.getLogger(__name__)


def _value(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        attribute = getattr(value, name, None)
        if attribute is not None:
            return attribute
    return default


def _parts(response: Any) -> list[Any]:
    candidates = _value(response, "candidates", default=[]) or []
    parts: list[Any] = []
    for candidate in candidates:
        content = _value(candidate, "content", default={}) or {}
        candidate_parts = _value(content, "parts", default=[]) or []
        if isinstance(candidate_parts, Sequence) and not isinstance(candidate_parts, str):
            parts.extend(candidate_parts)
    return parts


def _image_results(response: Any) -> list[ImageResult]:
    images: list[ImageResult] = []
    for part in _parts(response):
        inline_data = _value(part, "inlineData", "inline_data")
        if inline_data is None:
            continue
        encoded = _value(inline_data, "data")
        if not isinstance(encoded, str) or not encoded:
            continue
        mime_type = _value(
            inline_data, "mimeType", "mime_type", default="image/png"
        )
        images.append(ImageResult(base64_data=f"data:{mime_type};base64,{encoded}"))
    return images


def _text_result(response: Any) -> str:
    return "".join(
        text
        for part in _parts(response)
        if isinstance((text := _value(part, "text")), str)
    )


def _model_name(model: str) -> str:
    normalized = model.strip()
    if normalized.startswith("models/"):
        normalized = normalized.removeprefix("models/")
    return quote(normalized, safe="-._~")


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
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(300.0),
            headers={
                "User-Agent": COMPATIBLE_USER_AGENT,
                "x-goog-api-key": secret,
            },
        )

    def _generate_url(self, model: str) -> str:
        return f"{self.base_url}/models/{_model_name(model)}:generateContent"

    async def _post(self, model: str, payload: dict[str, Any]) -> Any:
        try:
            response = await self.client.post(self._generate_url(model), json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderRequestError(
                status_code=exc.response.status_code,
                response_content=exc.response.content,
                content_type=exc.response.headers.get("content-type"),
            ) from None
        except httpx.TimeoutException:
            raise ProviderTimeoutError() from None
        except (httpx.HTTPError, ValueError):
            raise ProviderRequestError() from None

    async def generate_image(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImage | None = None,
    ) -> GenerateResponse:
        started_at = perf_counter()
        image_config: dict[str, str] = {}
        if request.aspect_ratio:
            image_config["aspectRatio"] = request.aspect_ratio
        if request.resolution:
            image_config["imageSize"] = request.resolution
        generation_config: dict[str, Any] = {
            "responseModalities": ["TEXT", "IMAGE"],
        }
        if image_config:
            generation_config["imageConfig"] = image_config
        parts: list[dict[str, Any]] = [{"text": request.prompt}]
        if reference_image is not None:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": reference_image.content_type,
                        "data": base64.b64encode(reference_image.data).decode("ascii"),
                    }
                }
            )
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": parts,
                }
            ],
            "generationConfig": generation_config,
        }
        response = await self._post(request.model, payload)
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
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": content_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {"responseModalities": ["TEXT"]},
        }
        response = await self._post(model, payload)
        return AnalyzeResponse(provider=self.provider_id, model=model, text=_text_result(response))
