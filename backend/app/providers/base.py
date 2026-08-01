import base64
from collections.abc import Sequence
from typing import Any, Protocol

from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse


class ImageProvider(Protocol):
    async def generate_image(self, request: GenerateRequest) -> GenerateResponse:
        ...

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> AnalyzeResponse:
        ...


class ProviderError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ProviderNotFoundError(ProviderError):
    def __init__(self, provider_id: str) -> None:
        super().__init__("provider_not_found", f"Provider '{provider_id}' was not found")


class ProviderAuthError(ProviderError):
    def __init__(self) -> None:
        super().__init__("provider_auth", "Provider authentication failed")


class ProviderTimeoutError(ProviderError):
    def __init__(self) -> None:
        super().__init__("provider_timeout", "Provider request timed out")


class ProviderRequestError(ProviderError):
    def __init__(
        self,
        *,
        status_code: int | None = None,
        response_content: bytes | None = None,
        content_type: str | None = None,
    ) -> None:
        super().__init__("provider_request", "Provider request failed")
        self.status_code = status_code
        self.response_content = response_content
        self.content_type = content_type


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def normalize_image_results(response: Any) -> list[ImageResult]:
    data = _field(response, "data", []) or []
    results: list[ImageResult] = []
    for item in data:
        encoded = _field(item, "b64_json") or _field(item, "base64_data")
        results.append(
            ImageResult(
                url=_field(item, "url"),
                base64_data=encoded,
                revised_prompt=_field(item, "revised_prompt"),
            )
        )
    return results


def normalize_text(response: Any) -> str:
    output_text = _field(response, "output_text")
    if isinstance(output_text, str):
        return output_text

    choices = _field(response, "choices", []) or []
    if not choices:
        return ""
    content = _field(_field(choices[0], "message", {}), "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence):
        return "".join(
            part if isinstance(part, str) else str(_field(part, "text", ""))
            for part in content
        )
    return str(content)


def image_data_url(image_bytes: bytes, content_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{content_type};base64,{encoded}"
