from collections.abc import Sequence

from app.providers.base import ImageProvider, ProviderError
from app.schemas.analyze import AnalyzeResponse
from app.schemas.generate import (
    GenerateRequest,
    GenerateResponse,
    ReferenceImage,
    ReferenceImageInput,
)


class CustomProvider(ImageProvider):
    provider_id = "custom"
    label = "Custom"

    async def generate_image(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImageInput | None = None,
    ) -> GenerateResponse:
        raise ProviderError("provider_not_implemented", "Custom provider is not implemented")

    async def analyze_image(
        self, model: str, prompt: str, image_bytes: bytes, content_type: str
    ) -> AnalyzeResponse:
        raise ProviderError("provider_not_implemented", "Custom provider is not implemented")

    async def analyze_images(
        self, model: str, prompt: str, reference_images: Sequence[ReferenceImage]
    ) -> AnalyzeResponse:
        raise ProviderError("provider_not_implemented", "Custom provider is not implemented")
