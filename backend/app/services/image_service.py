from app.providers.registry import ProviderRegistry
from app.schemas.analyze import AnalyzeResponse
from app.schemas.generate import GenerateRequest, GenerateResponse


class ImageService:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    async def list_providers(self):
        return self.registry.list_models()

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        return await self.registry.resolve(request.provider).generate_image(request)

    async def analyze(
        self,
        provider: str,
        model: str,
        prompt: str,
        detail: str,
        image_bytes: bytes,
        content_type: str,
    ) -> AnalyzeResponse:
        return await self.registry.resolve(provider).analyze_image(
            model, prompt, image_bytes, content_type
        )
