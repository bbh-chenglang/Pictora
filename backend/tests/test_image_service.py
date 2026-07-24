import asyncio
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr

from app.providers.compatible_provider import CompatibleProvider
from app.providers.base import ProviderAuthError, ProviderRequestError, ProviderTimeoutError
from app.providers.openai_provider import OpenAIProvider
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.image_service import ImageService


class FakeImages:
    def __init__(self) -> None:
        self.request = None

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
        SimpleNamespace(provider="openai", model="gpt-image-1", prompt="draw", detail="high")
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
        "quality": "high",
    }
    image_url = client.chat.completions.request["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url == "data:image/png;base64,YWJj"


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
async def test_analyze_maps_sdk_authentication_error() -> None:
    error = openai.AuthenticationError(
        "analysis auth failure",
        response=httpx.Response(
            401,
            request=httpx.Request("POST", "https://api.example/v1/chat/completions"),
        ),
        body=None,
    )

    with pytest.raises(ProviderAuthError):
        await _analysis_provider_with_failure(error).analyze_image(
            "vision-model", "What is here?", b"abc", "image/png"
        )


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

    with pytest.raises(ProviderAuthError) as error:
        await provider.generate_image(
            SimpleNamespace(model="gpt-image-1", prompt="draw", detail="auto", provider="openai")
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
        await provider.generate_image(SimpleNamespace(model="gpt-image-1", prompt="draw", detail="auto", provider="openai"))

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
            SimpleNamespace(model="gpt-image-1", prompt="draw", detail="auto", provider="openai")
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
            SimpleNamespace(model="gpt-image-1", prompt="draw", detail="auto", provider="openai")
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
        SimpleNamespace(model="gpt-image-1", prompt="draw", detail="auto", provider="openai")
    )


@pytest.mark.asyncio
async def test_image_service_generates_prompt_batches_concurrently_with_timings() -> None:
    class ConcurrentProvider:
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
                provider="fake",
                model=request.model,
                images=[ImageResult(url=f"https://example.com/{request.prompt}.png")],
            )

    provider = ConcurrentProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    result = await service.generate(
        GenerateRequest(
            provider="fake",
            model="image-model",
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
async def test_image_service_infers_explicit_chinese_image_count() -> None:
    class CountProvider:
        async def generate_image(self, request):
            return GenerateResponse(
                provider="fake",
                model=request.model,
                images=[ImageResult(url="https://example.com/image.png")],
            )

    provider = CountProvider()
    service = ImageService(SimpleNamespace(resolve=lambda _: provider))
    result = await service.generate(
        GenerateRequest(provider="fake", model="image-model", prompt="帮我生成两张图片")
    )

    assert len(result.images) == 2
