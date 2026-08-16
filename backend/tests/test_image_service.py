import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from app.providers.compatible_provider import CompatibleProvider
from app.providers.base import ProviderRequestError, ProviderTimeoutError
from app.providers.openai_provider import OpenAIProvider
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import GenerationViewSpec, ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse, ReferenceImage, normalize_reference_images
from app.services.image_service import ImageService


class FakeImages:
    def __init__(self) -> None:
        self.request = None
        self.edit_request = None

    async def generate(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            data=[
                SimpleNamespace(
                    url="https://cdn.example/image.png",
                    b64_json=None,
                    revised_prompt="A revised prompt",
                )
            ]
        )

    async def edit(self, **kwargs):
        self.edit_request = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(url=None, b64_json="cmVzdWx0", revised_prompt=None)]
        )


class FakeCompletions:
    def __init__(self) -> None:
        self.request = None

    async def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="A red boat."))]
        )


class FakeClient:
    def __init__(self) -> None:
        self.images = FakeImages()
        self.chat = SimpleNamespace(completions=FakeCompletions())


@pytest.mark.asyncio
async def test_openai_provider_normalizes_generation_and_analysis() -> None:
    client = FakeClient()
    provider = OpenAIProvider(
        api_key=SecretStr("do-not-leak"),
        base_url="https://api.example/v1",
        model="gpt-image-1",
        client=client,
    )

    generated = await provider.generate_image(
        SimpleNamespace(
            provider="openai",
            model="gpt-image-1",
            prompt="draw",
            detail="high",
            size="1536x1152",
            count=1,
            output_format=None,
            background=None,
            output_compression=None,
            moderation=None,
        )
    )
    analysis = await provider.analyze_image("vision-model", "What is here?", b"abc", "image/png")

    assert generated.images[0].url == "https://cdn.example/image.png"
    assert generated.images[0].revised_prompt == "A revised prompt"
    assert generated.provider == "openai"
    assert isinstance(analysis, AnalyzeResponse)
    assert analysis.provider == "openai"
    assert analysis.model == "vision-model"
    assert analysis.text == "A red boat."
    assert client.images.request == {
        "model": "gpt-image-1",
        "prompt": "draw",
        "n": 1,
        "quality": "high",
        "size": "1536x1152",
    }
    image_url = client.chat.completions.request["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url == "data:image/png;base64,YWJj"


@pytest.mark.asyncio
async def test_openai_provider_uses_image_edit_for_reference_generation() -> None:
    client = FakeClient()
    provider = OpenAIProvider(
        api_key=SecretStr("do-not-leak"),
        base_url="https://api.example/v1",
        model="gpt-image-2",
        client=client,
    )

    response = await provider.generate_image(
        GenerateRequest(
            provider="openai",
            model="gpt-image-2",
            prompt="保留构图并增加自然光",
            detail="high",
            size="2048x1152",
            output_format="webp",
            background="opaque",
            output_compression=82,
            moderation="low",
        ),
        ReferenceImage(
            data=b"reference-bytes",
            content_type="image/jpeg",
            filename="room.jpg",
        ),
    )

    assert client.images.request is None
    edit_request = client.images.edit_request
    assert edit_request["model"] == "gpt-image-2"
    assert edit_request["prompt"] == "保留构图并增加自然光"
    assert edit_request["quality"] == "high"
    assert edit_request["size"] == "2048x1152"
    assert edit_request["n"] == 1
    assert edit_request["output_format"] == "webp"
    assert edit_request["background"] == "opaque"
    assert edit_request["output_compression"] == 82
    assert "moderation" not in edit_request
    assert edit_request["image"].name == "room.jpg"
    assert edit_request["image"].read() == b"reference-bytes"
    assert response.images[0].base64_data == "cmVzdWx0"


@pytest.mark.asyncio
async def test_openai_provider_forwards_multiple_reference_images() -> None:
    client = FakeClient()
    provider = OpenAIProvider(
        api_key=SecretStr("do-not-leak"),
        base_url="https://api.example/v1",
        model="gpt-image-2",
        client=client,
    )
    references = [
        ReferenceImage(data=b"room", content_type="image/jpeg", filename="room.jpg"),
        ReferenceImage(data=b"material", content_type="image/png", filename="material.png"),
    ]

    response = await provider.generate_image(
        GenerateRequest(provider="openai", model="gpt-image-2", prompt="融合参考图"),
        references,
    )
    await provider.analyze_images("vision-model", "比较图片", references)

    edit_images = client.images.edit_request["image"]
    assert [image.name for image in edit_images] == ["room.jpg", "material.png"]
    content = client.chat.completions.request["messages"][0]["content"]
    assert [part["image_url"]["url"] for part in content[1:]] == [
        "data:image/jpeg;base64,cm9vbQ==",
        "data:image/png;base64,bWF0ZXJpYWw=",
    ]


@pytest.mark.asyncio
async def test_openai_provider_forwards_native_generation_parameters() -> None:
    client = FakeClient()
    provider = OpenAIProvider(
        api_key=SecretStr("do-not-leak"),
        base_url="https://api.example/v1",
        model="gpt-image-2",
        client=client,
    )

    response = await provider.generate_image(
        GenerateRequest(
            provider="openai",
            model="gpt-image-2",
            prompt="draw a wallpaper",
            count=10,
            size="3840x2160",
            detail="medium",
            output_format="jpeg",
            background="opaque",
            output_compression=73,
            moderation="low",
        )
    )

    assert client.images.request == {
        "model": "gpt-image-2",
        "prompt": "draw a wallpaper",
        "n": 10,
        "size": "3840x2160",
        "quality": "medium",
        "output_format": "jpeg",
        "background": "opaque",
        "output_compression": 73,
        "moderation": "low",
    }
    assert response.images[0].mime_type == "image/jpeg"


@pytest.mark.asyncio
async def test_compatible_provider_returns_normalized_analysis_response() -> None:
    provider = CompatibleProvider(
        api_key=SecretStr("compatible-secret"),
        base_url="http://localhost:11434/v1",
        model="vision-model",
        client=FakeClient(),
    )

    result = await provider.analyze_image("vision-model", "What is here?", b"abc", "image/png")

    assert result == AnalyzeResponse(provider="compatible", model="vision-model", text="A red boat.")


def _analysis_provider_with_failure(error: Exception) -> OpenAIProvider:
    class FailingCompletions:
        async def create(self, **kwargs):
            raise error

    client = SimpleNamespace(chat=SimpleNamespace(completions=FailingCompletions()))
    return OpenAIProvider(
        api_key=SecretStr("analysis-secret"),
        base_url="https://api.example/v1",
        model="vision-model",
        client=client,
    )


@pytest.mark.asyncio
async def test_analyze_forwards_sdk_authentication_response() -> None:
    error = openai.AuthenticationError(
        "analysis auth failure",
        response=httpx.Response(
            401,
            content=b'{"error":{"message":"invalid key"}}',
            headers={"content-type": "application/json"},
            request=httpx.Request("POST", "https://api.example/v1/chat/completions"),
        ),
        body=None,
    )

    with pytest.raises(ProviderRequestError) as raised:
        await _analysis_provider_with_failure(error).analyze_image(
            "vision-model", "What is here?", b"abc", "image/png"
        )

    assert raised.value.status_code == 401
    assert raised.value.response_content == b'{"error":{"message":"invalid key"}}'
    assert raised.value.content_type == "application/json"


@pytest.mark.asyncio
async def test_analyze_maps_sdk_timeout_error() -> None:
    error = openai.APITimeoutError(
        request=httpx.Request("POST", "https://api.example/v1/chat/completions")
    )

    with pytest.raises(ProviderTimeoutError):
        await _analysis_provider_with_failure(error).analyze_image(
            "vision-model", "What is here?", b"abc", "image/png"
        )


@pytest.mark.asyncio
async def test_analyze_maps_sdk_request_error() -> None:
    error = openai.APIConnectionError(
        message="analysis request failure",
        request=httpx.Request("POST", "https://api.example/v1/chat/completions"),
    )

    with pytest.raises(ProviderRequestError):
        await _analysis_provider_with_failure(error).analyze_image(
            "vision-model", "What is here?", b"abc", "image/png"
        )


@pytest.mark.asyncio
async def test_analyze_does_not_translate_programming_errors() -> None:
    with pytest.raises(ValueError, match="invalid analysis setup"):
        await _analysis_provider_with_failure(ValueError("invalid analysis setup")).analyze_image(
            "vision-model", "What is here?", b"abc", "image/png"
        )


@pytest.mark.asyncio
async def test_provider_errors_do_not_expose_key() -> None:
    class FailingImages:
        async def generate(self, **kwargs):
            raise openai.AuthenticationError(
                "do-not-leak",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://api.example/v1/images/generations"),
                ),
                body=None,
            )

    client = SimpleNamespace(images=FailingImages())
    provider = OpenAIProvider(
        api_key=SecretStr("do-not-leak"),
        base_url="https://api.example/v1",
        model="gpt-image-1",
        client=client,
    )

    with pytest.raises(ProviderRequestError) as error:
        await provider.generate_image(
            GenerateRequest(provider="openai", model="gpt-image-1", prompt="draw")
        )

    assert "do-not-leak" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_maps_unknown_sdk_failure_to_request_error() -> None:
    class FailingImages:
        async def generate(self, **kwargs):
            raise openai.APIConnectionError(
                message="raw sdk payload with secret",
                request=httpx.Request("POST", "https://api.example/v1/images/generations"),
            )

    provider = OpenAIProvider(
        api_key=SecretStr("secret"),
        base_url="https://api.example/v1",
        model="gpt-image-1",
        client=SimpleNamespace(images=FailingImages()),
    )

    with pytest.raises(ProviderRequestError) as error:
        await provider.generate_image(
            GenerateRequest(provider="openai", model="gpt-image-1", prompt="draw")
        )

    assert "raw sdk payload" not in str(error.value)


@pytest.mark.asyncio
async def test_provider_maps_sdk_timeout_to_timeout_error() -> None:
    class FailingImages:
        async def generate(self, **kwargs):
            raise openai.APITimeoutError(
                request=httpx.Request("POST", "https://api.example/v1/images/generations")
            )

    provider = OpenAIProvider(
        api_key=SecretStr("secret"),
        base_url="https://api.example/v1",
        model="gpt-image-1",
        client=SimpleNamespace(images=FailingImages()),
    )

    with pytest.raises(ProviderTimeoutError):
        await provider.generate_image(
            GenerateRequest(provider="openai", model="gpt-image-1", prompt="draw")
        )


@pytest.mark.asyncio
async def test_programming_errors_are_not_translated() -> None:
    class FailingImages:
        async def generate(self, **kwargs):
            raise ValueError("invalid fake SDK setup")

    provider = OpenAIProvider(
        api_key=SecretStr("secret"),
        base_url="https://api.example/v1",
        model="gpt-image-1",
        client=SimpleNamespace(images=FailingImages()),
    )

    with pytest.raises(ValueError, match="invalid fake SDK setup"):
        await provider.generate_image(
            GenerateRequest(provider="openai", model="gpt-image-1", prompt="draw")
        )


@pytest.mark.asyncio
async def test_injected_falsy_client_is_preserved() -> None:
    class FalsyClient(FakeClient):
        def __bool__(self) -> bool:
            return False

    client = FalsyClient()
    provider = OpenAIProvider(
        api_key=SecretStr("secret"),
        base_url="https://api.example/v1",
        model="gpt-image-1",
        client=client,
    )

    assert provider.client is client
    await provider.generate_image(
        GenerateRequest(provider="openai", model="gpt-image-1", prompt="draw")
    )


@pytest.mark.asyncio
async def test_image_service_generates_gemini_slots_concurrently_with_timings() -> None:
    class ConcurrentProvider:
        provider_id = "gemini"
        active = 0
        max_active = 0
        calls = []

        async def generate_image(self, request):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(request.prompt)
            await asyncio.sleep(0.01)
            self.active -= 1
            return GenerateResponse(
                provider="gemini",
                model=request.model,
                images=[ImageResult(url=f"https://example.com/{request.prompt}.png")],
            )

    provider = ConcurrentProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    result = await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-3.1-flash-image",
            prompt="first",
            prompts=["first", "second"],
            count=2,
        )
    )

    assert len(result.images) == 4
    assert provider.calls == ["first", "first", "second", "second"]
    assert provider.max_active == 4
    assert all(image.generation_time_ms >= 1 for image in result.images)


@pytest.mark.asyncio
async def test_image_service_generates_one_slot_for_each_view_with_shared_references() -> None:
    class MultiViewProvider:
        provider_id = "gemini"

        def __init__(self) -> None:
            self.calls: list[tuple[str, int, list[str]]] = []

        async def generate_image(self, request, reference_image=None):
            references = normalize_reference_images(reference_image)
            self.calls.append((request.prompt, request.count, [item.filename or "" for item in references]))
            return GenerateResponse(
                provider="gemini",
                model=request.model,
                images=[ImageResult(url=f"https://example.com/{len(self.calls)}.png")],
            )

    provider = MultiViewProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    views = [
        GenerationViewSpec(key="person_front", label="正面", prompt="正面提示词"),
        GenerationViewSpec(key="person_back", label="背面", prompt="背面提示词"),
    ]
    references = [
        ReferenceImage(data=b"front", content_type="image/png", filename="front.png", category="person"),
        ReferenceImage(data=b"side", content_type="image/png", filename="side.png", category="person"),
    ]

    result = await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-3.1-flash-image",
            prompt="基础提示词",
            views=views,
        ),
        references,
    )

    assert len(result.images) == 2
    assert provider.calls == [
        ("正面提示词", 1, ["front.png", "side.png"]),
        ("背面提示词", 1, ["front.png", "side.png"]),
    ]
    assert [image.generation_position for image in result.images] == [0, 1]


@pytest.mark.asyncio
async def test_image_service_requires_subject_reference_for_multi_view() -> None:
    provider = SimpleNamespace(provider_id="gemini")
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    request = GenerateRequest(
        provider="gemini",
        model="gemini-3.1-flash-image",
        prompt="基础提示词",
        views=[GenerationViewSpec(key="person_front", label="正面", prompt="正面提示词")],
    )

    with pytest.raises(ValueError, match="person or object reference"):
        await service.normalize_request(request)
    with pytest.raises(ValueError, match="person or object reference"):
        await service.normalize_request(
            request,
            ReferenceImage(data=b"room", content_type="image/png", category="environment"),
        )


@pytest.mark.parametrize(
    ("provider_id", "model"),
    [
        ("openai", "gpt-image-2"),
        ("compatible", "gpt-image-2"),
        ("grok", "grok-imagine-image"),
    ],
)
@pytest.mark.asyncio
async def test_image_service_serializes_single_image_requests_for_gpt_and_grok(
    provider_id: str,
    model: str,
) -> None:
    class SerialProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []
            self.active = 0
            self.max_active = 0
            self.provider_id = provider_id

        async def generate_image(self, request):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append((request.prompt, request.count))
            await asyncio.sleep(0.001)
            self.active -= 1
            return GenerateResponse(
                provider=provider_id,
                model=request.model,
                images=[ImageResult(url=f"https://example.com/{len(self.calls)}.png")],
            )

    provider = SerialProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    reported_positions: list[int | None] = []

    async def report_image(image: ImageResult) -> None:
        reported_positions.append(image.generation_position)

    result = await service.generate(
        GenerateRequest(
            provider=provider_id,
            model=model,
            prompt="first",
            prompts=["first", "second"],
            count=2,
        ),
        on_image=report_image,
    )

    assert provider.calls == [
        ("first", 1),
        ("first", 1),
        ("second", 1),
        ("second", 1),
    ]
    assert provider.max_active == 1
    assert reported_positions == [0, 1, 2, 3]
    assert len(result.images) == 4


@pytest.mark.asyncio
async def test_image_service_continues_serial_slots_after_provider_error() -> None:
    class OneFailedSlotProvider:
        provider_id = "compatible"

        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderRequestError(status_code=400)
            return GenerateResponse(
                provider=self.provider_id,
                model=request.model,
                images=[ImageResult(url="https://example.com/result.png")],
            )

    provider = OneFailedSlotProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))

    result = await service.generate(
        GenerateRequest(
            provider="compatible",
            model="gpt-image-2",
            prompt="draw",
            count=2,
        )
    )

    assert provider.calls == 2
    assert [image.generation_position for image in result.images] == [1]
    assert [(failure.position, failure.error_code) for failure in result.failures] == [
        (0, "provider_request")
    ]


@pytest.mark.asyncio
async def test_image_service_retries_only_the_slot_with_an_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def skip_sleep(_: float) -> None:
        return None

    class EmptyOnceProvider:
        provider_id = "compatible"

        def __init__(self) -> None:
            self.calls: list[int] = []

        async def generate_image(self, request):
            self.calls.append(request.count)
            call_number = len(self.calls)
            images = [] if call_number == 2 else [
                ImageResult(url=f"https://example.com/image-{call_number}.png")
            ]
            return GenerateResponse(
                provider=self.provider_id,
                model=request.model,
                images=images,
            )

    monkeypatch.setattr(asyncio, "sleep", skip_sleep)
    monkeypatch.setattr("app.services.image_service.random.uniform", lambda *_: 0.0)
    provider = EmptyOnceProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))

    result = await service.generate(
        GenerateRequest(
            provider="compatible",
            model="gpt-image-2",
            prompt="draw",
            count=2,
        )
    )

    assert provider.calls == [1, 1, 1]
    assert [image.generation_position for image in result.images] == [0, 1]
    assert result.failures == []


@pytest.mark.asyncio
async def test_image_service_marks_a_slot_failed_after_empty_response_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def skip_sleep(_: float) -> None:
        return None

    class OneSlotAlwaysEmptyProvider:
        provider_id = "compatible"

        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, request):
            self.calls += 1
            return GenerateResponse(
                provider=self.provider_id,
                model=request.model,
                images=(
                    [ImageResult(url="https://example.com/image.png")]
                    if self.calls == 1
                    else []
                ),
            )

    monkeypatch.setattr(asyncio, "sleep", skip_sleep)
    monkeypatch.setattr("app.services.image_service.random.uniform", lambda *_: 0.0)
    provider = OneSlotAlwaysEmptyProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))

    result = await service.generate(
        GenerateRequest(
            provider="compatible",
            model="gpt-image-2",
            prompt="draw",
            count=2,
        )
    )

    assert provider.calls == 5
    assert [image.generation_position for image in result.images] == [0]
    assert [(failure.position, failure.error_code) for failure in result.failures] == [
        (1, "partial_generation")
    ]


@pytest.mark.asyncio
async def test_image_service_allows_five_minutes_per_generated_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeout_values: list[int] = []

    class TimeoutContext:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    def capture_timeout(seconds: int):
        timeout_values.append(seconds)
        return TimeoutContext()

    class ImmediateProvider:
        async def generate_image(self, request):
            return GenerateResponse(
                provider="openai",
                model=request.model,
                images=[ImageResult(url="https://example.com/image.png")],
            )

    monkeypatch.setattr(asyncio, "timeout", capture_timeout)
    service = ImageService(SimpleNamespace(resolve=lambda _: ImmediateProvider()))

    await service.generate(
        GenerateRequest(
                provider="openai",
                model="gpt-image-1",
            prompt="draw",
            count=3,
        )
    )

    assert timeout_values == [900]


@pytest.mark.asyncio
async def test_image_service_skips_only_cancelled_serial_slot() -> None:
    class SerialProvider:
        provider_id = "compatible"

        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, request):
            self.calls += 1
            return GenerateResponse(
                provider="compatible",
                model=request.model,
                images=[ImageResult(url=f"https://example.com/{self.calls}.png")],
            )

    async def should_skip(position: int) -> bool:
        return position == 1

    provider = SerialProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    result = await service.generate(
        GenerateRequest(provider="compatible", model="gpt-image-2", prompt="draw", count=3),
        should_skip=should_skip,
    )

    assert provider.calls == 2
    assert [image.generation_position for image in result.images] == [0, 2]
    assert [(failure.position, failure.error_code) for failure in result.failures] == [
        (1, "generation_cancelled")
    ]


@pytest.mark.asyncio
async def test_image_service_treats_provider_error_as_cancelled_after_active_slot_cancel() -> None:
    class FailingProvider:
        provider_id = "compatible"

        async def generate_image(self, request):
            raise ProviderRequestError(status_code=400)

    checks = 0

    async def should_skip(position: int) -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    service = ImageService(SimpleNamespace(resolve=lambda _: FailingProvider()))
    result = await service.generate(
        GenerateRequest(provider="compatible", model="gpt-image-2", prompt="draw"),
        should_skip=should_skip,
    )

    assert result.images == []
    assert [(failure.position, failure.error_code) for failure in result.failures] == [
        (0, "generation_cancelled")
    ]


@pytest.mark.asyncio
async def test_image_service_maps_batch_timeout_to_provider_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ExpiredTimeout:
        async def __aenter__(self):
            raise TimeoutError

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(asyncio, "timeout", lambda _: ExpiredTimeout())

    class ImmediateProvider:
        async def generate_image(self, request):
            return GenerateResponse(
                provider="fake",
                model=request.model,
                images=[ImageResult(url="https://example.com/image.png")],
            )

    service = ImageService(SimpleNamespace(resolve=lambda _: ImmediateProvider()))

    with pytest.raises(ProviderTimeoutError):
        await service.generate(
            GenerateRequest(provider="openai", model="gpt-image-1", prompt="draw")
        )


@pytest.mark.asyncio
async def test_image_service_infers_explicit_chinese_image_count() -> None:
    class CountProvider:
        async def generate_image(self, request):
            return GenerateResponse(
                provider="openai",
                model=request.model,
                images=[ImageResult(url="https://example.com/image.png")],
            )

    provider = CountProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    result = await service.generate(
        GenerateRequest(provider="openai", model="gpt-image-1", prompt="帮我生成两张图片")
    )

    assert len(result.images) == 2


@pytest.mark.parametrize("status_code", [429, 502, 503, 504, 524])
@pytest.mark.asyncio
async def test_image_service_retries_transient_provider_statuses(
    status_code: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    class FlakyProvider:
        provider_id = "gemini"

        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderRequestError(status_code=status_code)
            return GenerateResponse(
                provider="gemini",
                model=request.model,
                images=[ImageResult(url="https://example.com/result.png")],
            )

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    monkeypatch.setattr("app.services.image_service.random.uniform", lambda *_: 0.0)
    provider = FlakyProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))

    result = await service.generate(
        GenerateRequest(provider="gemini", model="gemini-3.1-flash-image", prompt="draw")
    )

    assert provider.calls == 2
    assert delays == [1.0]
    assert len(result.images) == 1


@pytest.mark.asyncio
async def test_image_service_caps_rate_limit_retry_after_at_thirty_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    class RateLimitedOnceProvider:
        provider_id = "gemini"

        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderRequestError(
                    status_code=429,
                    retry_after_seconds=90,
                )
            return GenerateResponse(
                provider="gemini",
                model=request.model,
                images=[ImageResult(url="https://example.com/result.png")],
            )

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    provider = RateLimitedOnceProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))

    await service.generate(
        GenerateRequest(provider="gemini", model="gemini-3.1-flash-image", prompt="draw")
    )

    assert provider.calls == 2
    assert delays == [30.0]


@pytest.mark.asyncio
async def test_image_service_stops_after_three_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def record_sleep(delay: float) -> None:
        delays.append(delay)

    class UnavailableProvider:
        provider_id = "gemini"

        def __init__(self) -> None:
            self.calls = 0

        async def generate_image(self, request):
            self.calls += 1
            raise ProviderRequestError(status_code=502)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    monkeypatch.setattr("app.services.image_service.random.uniform", lambda *_: 0.0)
    provider = UnavailableProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))

    with pytest.raises(ProviderRequestError) as raised:
        await service.generate(
            GenerateRequest(provider="gemini", model="gemini-3.1-flash-image", prompt="draw")
        )

    assert raised.value.status_code == 502
    assert provider.calls == 4
    assert delays == [1.0, 2.0, 4.0]


@pytest.mark.asyncio
async def test_image_service_keeps_successful_slots_when_one_slot_exhausts_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def skip_sleep(_: float) -> None:
        return None

    class PartiallyUnavailableProvider:
        provider_id = "gemini"

        def __init__(self) -> None:
            self.calls: list[str] = []

        async def generate_image(self, request):
            self.calls.append(request.prompt)
            if request.prompt == "second":
                raise ProviderRequestError(status_code=502)
            return GenerateResponse(
                provider="gemini",
                model=request.model,
                images=[ImageResult(url=f"https://example.com/{request.prompt}.png")],
            )

    monkeypatch.setattr(asyncio, "sleep", skip_sleep)
    monkeypatch.setattr("app.services.image_service.random.uniform", lambda *_: 0.0)
    provider = PartiallyUnavailableProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))

    result = await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-3.1-flash-image",
            prompt="first",
            prompts=["first", "second", "third"],
        )
    )

    assert [image.generation_position for image in result.images] == [0, 2]
    assert [(failure.position, failure.error_code) for failure in result.failures] == [
        (1, "provider_request")
    ]
    assert provider.calls.count("first") == 1
    assert provider.calls.count("second") == 4
    assert provider.calls.count("third") == 1
