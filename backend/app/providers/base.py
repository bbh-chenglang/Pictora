import base64
import json
import re
from collections.abc import Sequence
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import (
    GenerateRequest,
    GenerateResponse,
    ReferenceImage,
    ReferenceImageInput,
)


class ImageProvider(Protocol):
    async def generate_image(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImageInput | None = None,
    ) -> GenerateResponse:
        ...

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> AnalyzeResponse:
        ...

    async def analyze_images(
        self, model: str, prompt: str, reference_images: Sequence[ReferenceImage]
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
        retry_after_seconds: float | None = None,
    ) -> None:
        message = "Provider request failed"
        if status_code is not None:
            message += f" (HTTP {status_code})"
        upstream_message = _safe_upstream_error_message(response_content)
        if upstream_message:
            message += f": {upstream_message}"
        super().__init__("provider_request", message)
        self.status_code = status_code
        self.response_content = response_content
        self.content_type = content_type
        self.retry_after_seconds = retry_after_seconds


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


_MAX_ERROR_BODY_BYTES = 64 * 1024
_MAX_ERROR_MESSAGE_LENGTH = 400
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_KNOWN_KEY_PREFIX = re.compile(r"(?i)\b(?:sk|xai)-[a-z0-9_-]{8,}\b")
_LABELED_SECRET = re.compile(
    r"(?i)\b(api[_ -]?key|authorization|access[_ -]?token|token)"
    r"(\s*[:=]\s*)[\"']?[^\s,\"';]+"
)


def _extract_error_message(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, (int, float, bool)):
        return str(payload)
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            for field in ("message", "detail"):
                message = _extract_error_message(error.get(field))
                if message:
                    return message
        elif isinstance(error, str):
            return error
        for field in ("message", "detail"):
            message = _extract_error_message(payload.get(field))
            if message:
                return message
    if isinstance(payload, list):
        messages = [
            message
            for item in payload[:3]
            if (message := _extract_error_message(item))
        ]
        return "; ".join(messages) or None
    return None


def _safe_upstream_error_message(response_content: bytes | None) -> str | None:
    if not response_content or len(response_content) > _MAX_ERROR_BODY_BYTES:
        return None
    try:
        payload = json.loads(response_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    message = _extract_error_message(payload)
    if not message:
        return None
    message = " ".join(message.split())
    message = _BEARER_TOKEN.sub("Bearer [REDACTED]", message)
    message = _KNOWN_KEY_PREFIX.sub("[REDACTED]", message)
    message = _LABELED_SECRET.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        message,
    )
    if len(message) > _MAX_ERROR_MESSAGE_LENGTH:
        message = f"{message[:_MAX_ERROR_MESSAGE_LENGTH - 3].rstrip()}..."
    return message or None


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
                mime_type=_field(item, "mime_type"),
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
