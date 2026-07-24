from app.providers.base import ImageProvider, ProviderError
from app.schemas.generate import GenerateRequest, GenerateResponse


class CustomProvider(ImageProvider):
    provider_id = "custom"
    label = "Custom"

    async def generate_image(self, request: GenerateRequest) -> GenerateResponse:
        raise ProviderError("provider_not_implemented", "Custom provider is not implemented")

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> str:
        raise ProviderError("provider_not_implemented", "Custom provider is not implemented")
