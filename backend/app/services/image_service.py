import asyncio
import inspect
import logging
import random
import re
from collections.abc import Awaitable, Callable
from time import perf_counter

from app.providers.base import ProviderError, ProviderRequestError, ProviderTimeoutError
from app.observability import log_context
from app.providers.registry import ProviderRegistry
from app.model_capabilities import (
    get_model_capabilities,
    normalize_generation_request,
)
from app.repositories.api_key_config_repository import ApiKeyConfigNotFoundError
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import (
    GenerateRequest,
    GenerateResponse,
    ImageGenerationFailure,
    ReferenceImage,
    ReferenceImageInput,
    normalize_reference_images,
)


logger = logging.getLogger(__name__)
MAX_TOTAL_OUTPUT_COUNT = 40
RETRYABLE_PROVIDER_STATUS_CODES = {429, 502, 503, 504, 524}
MAX_PROVIDER_RETRIES = 3
MAX_RETRY_AFTER_SECONDS = 30.0


class ImageService:
    def __init__(self, registry: ProviderRegistry, config_repository=None, user_id: int | None = None, provider_factory=None) -> None:
        self.registry = registry
        self.config_repository = config_repository
        self.user_id = user_id
        self.provider_factory = provider_factory or ProviderRegistry.from_api_key_config
        self._config_providers: dict[int, object] = {}

    async def list_providers(self):
        return self.registry.list_models()

    async def normalize_request(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImageInput | None = None,
    ) -> GenerateRequest:
        if request.api_key_config_id is not None:
            provider = await self._provider_for_config(request.api_key_config_id)
            provider_id = provider.provider_id
        else:
            provider = self.registry.resolve(request.provider)
            provider_id = getattr(provider, "provider_id", request.provider)
        normalized = normalize_generation_request(
            request.model_copy(update={"provider": provider_id})
        )
        reference_images = normalize_reference_images(reference_image)
        reference_count = len(reference_images)
        capability = get_model_capabilities(normalized.provider, normalized.model)
        if reference_count > capability.max_reference_images:
            raise ValueError(
                f"{capability.model} supports at most "
                f"{capability.max_reference_images} reference images"
            )
        if normalized.views is not None and not any(
            image.category in {"person", "object"} for image in reference_images
        ):
            raise ValueError(
                "multi-view generation requires at least one person or object reference image"
            )
        per_prompt_count = self.effective_count_per_prompt(normalized)
        if per_prompt_count > capability.max_output_count:
            raise ValueError(
                f"{capability.model} supports at most {capability.max_output_count} images per prompt"
            )
        if self.expected_image_count(normalized) > MAX_TOTAL_OUTPUT_COUNT:
            raise ValueError(
                f"A generation task supports at most {MAX_TOTAL_OUTPUT_COUNT} images in total"
            )
        return normalized

    async def generate(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImageInput | None = None,
        *,
        on_image: Callable[[ImageResult], Awaitable[None]] | None = None,
        should_skip: Callable[[int], Awaitable[bool]] | None = None,
    ) -> GenerateResponse:
        effective_request = await self.normalize_request(request, reference_image)
        if request.api_key_config_id is not None:
            provider = await self._provider_for_config(request.api_key_config_id)
        else:
            provider = self.registry.resolve(effective_request.provider)
        prompts = (
            [view.prompt for view in effective_request.views]
            if effective_request.views is not None
            else effective_request.prompts or [effective_request.prompt]
        )
        count = self.effective_count_per_prompt(effective_request)
        slot_prompts = [prompt for prompt in prompts for _ in range(count)]
        job_positions = [[position] for position in range(len(slot_prompts))]
        provider_id = getattr(provider, "provider_id", "")
        serial_slots = provider_id in {"openai", "compatible", "grok"}
        skipped_positions: set[int] = set()

        async def generate_slot(prompt: str, positions: list[int]):
            if should_skip is not None:
                for position in positions:
                    if await should_skip(position):
                        skipped_positions.add(position)
                if all(position in skipped_positions for position in positions):
                    return GenerateResponse(
                        provider=effective_request.provider,
                        model=effective_request.model,
                        images=[],
                    )
            try:
                result = await self._generate_one_with_retry(
                    provider,
                    effective_request,
                    prompt,
                    reference_image,
                )
            except ProviderError as exc:
                if should_skip is not None:
                    for position in positions:
                        if await should_skip(position):
                            skipped_positions.add(position)
                    if all(position in skipped_positions for position in positions):
                        return GenerateResponse(
                            provider=effective_request.provider,
                            model=effective_request.model,
                            images=[],
                        )
                return exc
            if should_skip is not None:
                for position in positions:
                    if await should_skip(position):
                        skipped_positions.add(position)
            if on_image is not None:
                for offset, image in enumerate(result.images[:len(positions)]):
                    if positions[offset] in skipped_positions:
                        continue
                    await on_image(image.model_copy(
                        update={"generation_position": positions[offset]},
                    ))
            return result

        try:
            timeout_seconds = (len(slot_prompts) if serial_slots else count) * 300
            async with asyncio.timeout(timeout_seconds):
                if serial_slots:
                    results = []
                    for prompt, positions in zip(slot_prompts, job_positions, strict=True):
                        results.append(await generate_slot(prompt, positions))
                else:
                    jobs = [
                        generate_slot(prompt, positions)
                        for prompt, positions in zip(slot_prompts, job_positions, strict=True)
                    ]
                    results = await asyncio.gather(*jobs, return_exceptions=True)
        except TimeoutError:
            raise ProviderTimeoutError() from None

        unexpected = next(
            (
                result
                for result in results
                if isinstance(result, BaseException)
                and not isinstance(result, ProviderError)
            ),
            None,
        )
        if unexpected is not None:
            raise unexpected

        images = []
        failures: list[ImageGenerationFailure] = []
        first_provider_error: ProviderError | None = None
        for positions, result in zip(job_positions, results, strict=True):
            if isinstance(result, ProviderError):
                first_provider_error = first_provider_error or result
                failures.extend(
                    ImageGenerationFailure(
                        position=position,
                        error_code=result.code,
                        error_message=result.message,
                    )
                    for position in positions
                )
                continue

            returned_positions: set[int] = set()
            for offset, image in enumerate(result.images):
                if offset >= len(positions):
                    break
                position = positions[offset]
                if position in skipped_positions:
                    continue
                returned_positions.add(position)
                images.append(image.model_copy(update={"generation_position": position}))
            failures.extend(
                ImageGenerationFailure(
                    position=position,
                    error_code=(
                        "generation_cancelled"
                        if position in skipped_positions
                        else "partial_generation"
                    ),
                    error_message=(
                        "该图片生成已取消"
                        if position in skipped_positions
                        else "服务商未返回该位置的图片"
                    ),
                )
                for position in positions
                if position not in returned_positions
            )

        if not images and first_provider_error is not None:
            raise first_provider_error
        return GenerateResponse(
            provider=effective_request.provider,
            model=effective_request.model,
            images=images,
            failures=failures,
        )

    async def _generate_one_with_retry(
        self,
        provider,
        request: GenerateRequest,
        prompt: str,
        reference_image: ReferenceImageInput | None = None,
        *,
        count: int = 1,
    ) -> GenerateResponse:
        for retry_index in range(MAX_PROVIDER_RETRIES + 1):
            try:
                response = await self._generate_one(
                    provider,
                    request,
                    prompt,
                    reference_image,
                    count=count,
                )
            except ProviderRequestError as exc:
                if (
                    exc.status_code not in RETRYABLE_PROVIDER_STATUS_CODES
                    or retry_index >= MAX_PROVIDER_RETRIES
                ):
                    raise
                delay = self._retry_delay(exc, retry_index)
                logger.warning(
                    "image_generation step=provider_call_retry provider=%s model=%s "
                    "status_code=%d retry=%d delay_seconds=%.3f %s",
                    getattr(provider, "provider_id", request.provider),
                    request.model,
                    exc.status_code,
                    retry_index + 1,
                    delay,
                    " ".join(f"{key}={value}" for key, value in log_context().items()),
                )
                await asyncio.sleep(delay)
                continue
            if response.images or retry_index >= MAX_PROVIDER_RETRIES:
                return response
            delay = self._retry_delay(None, retry_index)
            logger.warning(
                "image_generation step=provider_call_retry provider=%s model=%s "
                "reason=empty_response retry=%d delay_seconds=%.3f %s",
                getattr(provider, "provider_id", request.provider),
                request.model,
                retry_index + 1,
                delay,
                " ".join(f"{key}={value}" for key, value in log_context().items()),
            )
            await asyncio.sleep(delay)
        raise RuntimeError("Provider retry loop exited unexpectedly")

    @staticmethod
    def _retry_delay(error: ProviderRequestError | None, retry_index: int) -> float:
        if (
            error is not None
            and error.status_code == 429
            and error.retry_after_seconds is not None
        ):
            return min(MAX_RETRY_AFTER_SECONDS, max(0.0, error.retry_after_seconds))
        base_delay = float(2**retry_index)
        jitter = random.uniform(0.0, min(1.0, base_delay * 0.25))
        return base_delay + jitter

    async def _provider_for_config(self, config_id: int):
        cached = self._config_providers.get(config_id)
        if cached is not None:
            return cached
        if self.config_repository is None or self.user_id is None:
            raise ApiKeyConfigNotFoundError(config_id)
        config = await self.config_repository.get_owned(self.user_id, config_id)
        if config is None:
            raise ApiKeyConfigNotFoundError(config_id)
        provider = self.provider_factory(config)
        self._config_providers[config_id] = provider
        return provider

    async def aclose(self) -> None:
        providers = list({id(provider): provider for provider in self._config_providers.values()}.values())
        self._config_providers.clear()
        for provider in providers:
            close = getattr(provider, "aclose", None)
            if close is None:
                client = getattr(provider, "client", None)
                close = getattr(client, "aclose", None) or getattr(client, "close", None)
            if close is None:
                continue
            result = close()
            if inspect.isawaitable(result):
                await result

    @staticmethod
    def _prompt_count(prompt: str) -> int:
        matches = re.findall(r"(?:生成|绘制|输出|创建)[^\n]{0,8}?(\d+|一|两|二|三|四)\s*(?:张|幅|个)", prompt)
        if not matches:
            return 1
        chinese_counts = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4}
        return chinese_counts[matches[0]] if matches[0] in chinese_counts else int(matches[0])

    @classmethod
    def effective_count_per_prompt(cls, request: GenerateRequest) -> int:
        if request.views is not None:
            return 1
        prompts = request.prompts or [request.prompt]
        if request.count > 1:
            return request.count
        return max(request.count, *(cls._prompt_count(prompt) for prompt in prompts))

    @classmethod
    def expected_image_count(cls, request: GenerateRequest) -> int:
        if request.views is not None:
            return len(request.views)
        prompts = request.prompts or [request.prompt]
        return len(prompts) * cls.effective_count_per_prompt(request)

    async def _generate_one(
        self,
        provider,
        request: GenerateRequest,
        prompt: str,
        reference_image: ReferenceImageInput | None = None,
        *,
        count: int = 1,
    ) -> GenerateResponse:
        started_at = perf_counter()
        logger.info(
            "image_generation step=provider_call_started provider=%s model=%s %s",
            getattr(provider, "provider_id", request.provider),
            request.model,
            " ".join(f"{key}={value}" for key, value in log_context().items()),
        )
        try:
            generation_request = request.model_copy(update={"prompt": prompt, "count": count})
            response = (
                await provider.generate_image(generation_request, reference_image)
                if reference_image is not None
                else await provider.generate_image(generation_request)
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
        api_key_config_id: int | None = None,
        reference_images: ReferenceImageInput | None = None,
    ) -> AnalyzeResponse:
        resolved_provider = (
            await self._provider_for_config(api_key_config_id)
            if api_key_config_id is not None
            else self.registry.resolve(provider)
        )
        images = normalize_reference_images(reference_images)
        if len(images) > 1:
            return await resolved_provider.analyze_images(model, prompt, images)
        return await resolved_provider.analyze_image(model, prompt, image_bytes, content_type)
