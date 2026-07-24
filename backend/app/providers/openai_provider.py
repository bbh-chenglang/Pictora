from typing import Any

from openai import (
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    PermissionDeniedError,
)
from pydantic import SecretStr

from app.schemas.analyze import AnalyzeResponse
from app.providers.base import (
    ImageProvider,
    ProviderAuthError,
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
        self.client = (
            client if client is not None else AsyncOpenAI(api_key=secret, base_url=base_url)
        )

    async def generate_image(self, request: GenerateRequest) -> GenerateResponse:
        arguments: dict[str, Any] = {"model": request.model, "prompt": request.prompt}
        if request.detail in {"low", "high"}:
            arguments["quality"] = request.detail
        try:
            response = await self.client.images.generate(**arguments)
        except (AuthenticationError, PermissionDeniedError):
            raise ProviderAuthError() from None
        except APITimeoutError:
            raise ProviderTimeoutError() from None
        except APIError:
            raise ProviderRequestError() from None
        images = normalize_image_results(response)
        return GenerateResponse(provider=self.provider_id, model=request.model, images=images)

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
        except (AuthenticationError, PermissionDeniedError):
            raise ProviderAuthError() from None
        except APITimeoutError:
            raise ProviderTimeoutError() from None
        except APIError:
            raise ProviderRequestError() from None
        return AnalyzeResponse(provider=self.provider_id, model=model, text=normalize_text(response))
