import asyncio
import logging
import re
from time import perf_counter

from app.providers.base import ProviderTimeoutError
from app.observability import log_context
from app.providers.registry import ProviderRegistry
from app.repositories.api_key_config_repository import ApiKeyConfigNotFoundError
from app.schemas.analyze import AnalyzeResponse
from app.schemas.generate import GenerateRequest, GenerateResponse


logger = logging.getLogger(__name__)


class ImageService:
    def __init__(self, registry: ProviderRegistry, config_repository=None, user_id: int | None = None, provider_factory=None) -> None:
        self.registry = registry
        self.config_repository = config_repository
        self.user_id = user_id
        self.provider_factory = provider_factory or ProviderRegistry.from_api_key_config

    async def list_providers(self):
        return self.registry.list_models()

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        effective_request = request
        if request.api_key_config_id is not None:
            if self.config_repository is None or self.user_id is None:
                raise ApiKeyConfigNotFoundError(request.api_key_config_id)
            config = await self.config_repository.get_owned(self.user_id, request.api_key_config_id)
            if config is None:
                raise ApiKeyConfigNotFoundError(request.api_key_config_id)
            provider = self.provider_factory(config)
            effective_request = request.model_copy(
                update={"provider": provider.provider_id, "model": request.model.strip() or config.model}
            )
        else:
            provider = self.registry.resolve(request.provider)
        prompts = effective_request.prompts or [effective_request.prompt]
        count = effective_request.count if effective_request.count > 1 else max(
            effective_request.count, *(self._prompt_count(prompt) for prompt in prompts)
        )
        try:
            async with asyncio.timeout(count * 300):
                jobs = [
                    self._generate_one(provider, effective_request, prompt)
                    for prompt in prompts
                    for _ in range(count)
                ]
                responses = await asyncio.gather(*jobs)
        except TimeoutError:
            raise ProviderTimeoutError() from None
        return GenerateResponse(
            provider=effective_request.provider,
            model=effective_request.model,
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
        logger.info(
            "image_generation step=provider_call_started provider=%s model=%s %s",
            getattr(provider, "provider_id", request.provider),
            request.model,
            " ".join(f"{key}={value}" for key, value in log_context().items()),
        )
        try:
            response = await provider.generate_image(
                request.model_copy(update={"prompt": prompt, "count": 1})
            )
        except Exception:
            logger.error(
                "image_generation step=provider_call_failed duration_ms=%d provider=%s model=%s %s",
                max(1, round((perf_counter() - started_at) * 1000)),
                getattr(provider, "provider_id", request.provider),
                request.model,
                " ".join(f"{key}={value}" for key, value in log_context().items()),
            )
            raise
        elapsed_ms = max(1, round((perf_counter() - started_at) * 1000))
        logger.info(
            "image_generation step=provider_call_completed duration_ms=%d provider=%s model=%s image_count=%d %s",
            elapsed_ms,
            getattr(provider, "provider_id", request.provider),
            request.model,
            len(response.images),
            " ".join(f"{key}={value}" for key, value in log_context().items()),
        )
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
