from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.providers.base import ProviderAuthError, ProviderRequestError
from app.providers.openai_provider import OpenAIProvider


class FakeImages:
    def __init__(self) -> None:
        self.request = None

    def generate(self, **kwargs):
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

    def create(self, **kwargs):
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
    text = await provider.analyze_image("vision-model", "What is here?", b"abc", "image/png")

    assert generated.images[0].url == "https://cdn.example/image.png"
    assert generated.images[0].revised_prompt == "A revised prompt"
    assert generated.provider == "openai"
    assert text == "A red boat."
    assert client.images.request == {
        "model": "gpt-image-1",
        "prompt": "draw",
        "quality": "high",
    }
    image_url = client.chat.completions.request["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url == "data:image/png;base64,YWJj"


class AuthenticationError(Exception):
    pass


@pytest.mark.asyncio
async def test_provider_errors_do_not_expose_key() -> None:
    class FailingImages:
        def generate(self, **kwargs):
            raise AuthenticationError("do-not-leak")

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
        def generate(self, **kwargs):
            raise RuntimeError("raw sdk payload with secret")

    provider = OpenAIProvider(
        api_key=SecretStr("secret"),
        base_url="https://api.example/v1",
        model="gpt-image-1",
        client=SimpleNamespace(images=FailingImages()),
    )

    with pytest.raises(ProviderRequestError) as error:
        await provider.generate_image(SimpleNamespace(model="gpt-image-1", prompt="draw", detail="auto", provider="openai"))

    assert "raw sdk payload" not in str(error.value)
