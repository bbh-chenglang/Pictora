import asyncio
import re
from time import perf_counter

from app.providers.registry import ProviderRegistry
from app.schemas.analyze import AnalyzeResponse
from app.schemas.generate import GenerateRequest, GenerateResponse


class ImageService:
    def __init__(self, registry: ProviderRegistry) -> None:
        self.registry = registry

    async def list_providers(self):
        return self.registry.list_models()

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        provider = self.registry.resolve(request.provider)
        prompts = request.prompts or [request.prompt]
        count = request.count if request.count > 1 else max(
            request.count, *(self._prompt_count(prompt) for prompt in prompts)
        )
        jobs = [self._generate_one(provider, request, prompt) for prompt in prompts for _ in range(count)]
        responses = await asyncio.gather(*jobs)
        return GenerateResponse(
            provider=request.provider,
            model=request.model,
            images=[image for response in responses for image in response.images],
        )

    @staticmethod
    def _prompt_count(prompt: str) -> int:
        matches = re.findall(r"(?:生成|绘制|输出|创建)[^\n]{0,8}?(\d+|一|两|二|三|四)\s*(?:张|幅|个)", prompt)
        if not matches:
            return 1
        chinese_counts = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4}
        return chinese_counts[matches[0]] if matches[0] in chinese_counts else int(matches[0])

    async def _generate_one(self, provider, request: GenerateRequest, prompt: str) -> GenerateResponse:
        started_at = perf_counter()
        response = await provider.generate_image(
            request.model_copy(update={"prompt": prompt, "count": 1})
        )
        elapsed_ms = max(1, round((perf_counter() - started_at) * 1000))
        return response.model_copy(
            update={
                "images": [image.model_copy(update={"generation_time_ms": elapsed_ms}) for image in response.images]
            }
        )

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
