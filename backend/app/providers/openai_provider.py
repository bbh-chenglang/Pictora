from typing import Any

from openai import OpenAI
from pydantic import SecretStr

from app.providers.base import (
    ImageProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRequestError,
    ProviderTimeoutError,
    image_data_url,
    normalize_image_results,
    normalize_text,
)
from app.schemas.generate import GenerateRequest, GenerateResponse


class OpenAIProvider(ImageProvider):
    provider_id = "openai"
    label = "OpenAI"

    def __init__(
        self,
        api_key: SecretStr | str,
        base_url: str,
        model: str,
        client: Any | None = None,
    ) -> None:
        secret = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self.model = model
        self.client = client or OpenAI(api_key=secret, base_url=base_url)

    async def generate_image(self, request: GenerateRequest) -> GenerateResponse:
        arguments: dict[str, Any] = {"model": request.model, "prompt": request.prompt}
        if request.detail in {"low", "high"}:
            arguments["quality"] = request.detail
        try:
            response = self.client.images.generate(**arguments)
            images = normalize_image_results(response)
        except Exception as error:
            raise self._translate_error(error) from None
        return GenerateResponse(provider=self.provider_id, model=request.model, images=images)

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> str:
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
            response = self.client.chat.completions.create(**arguments)
            return normalize_text(response)
        except Exception as error:
            raise self._translate_error(error) from None

    @staticmethod
    def _translate_error(error: Exception) -> ProviderError:
        name = type(error).__name__.lower()
        if "auth" in name or "permission" in name:
            return ProviderAuthError()
        if "timeout" in name:
            return ProviderTimeoutError()
        return ProviderRequestError()
