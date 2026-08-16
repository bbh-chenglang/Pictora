from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import SecretStr, ValidationError

from app.providers.base import ProviderRequestError
from app.providers.grok_provider import GrokProvider
from app.schemas.generate import GenerateRequest, ReferenceImage
from app.model_capabilities import normalize_generation_request


class FakeGrokImages:
    def __init__(self) -> None:
        self.request = None

    async def generate(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            data=[SimpleNamespace(url=None, b64_json="Z3Jvaw==", mime_type="image/webp")]
        )


class FakeGrokClient:
    def __init__(self) -> None:
        self.images = FakeGrokImages()
        self.post_request = None

    async def post(self, path, **kwargs):
        self.post_request = (path, kwargs)
        return SimpleNamespace(
            data=[SimpleNamespace(url=None, b64_json="ZWRpdA==", mime_type="image/png")]
        )


def grok_provider(client: FakeGrokClient) -> GrokProvider:
    return GrokProvider(
        SecretStr("grok-secret"),
        "https://relay.example/v1",
        "grok-imagine-image",
        "Grok",
        client=client,
    )


@pytest.mark.asyncio
async def test_grok_generation_uses_native_dimensions_and_base64() -> None:
    client = FakeGrokClient()
    response = await grok_provider(client).generate_image(
        GenerateRequest(
            provider="grok",
            model="grok-imagine-image",
            prompt="海边奔跑的人",
            size="16:9",
            aspect_ratio="16:9",
            resolution="1K",
        )
    )

    assert client.images.request == {
        "model": "grok-imagine-image",
        "prompt": "海边奔跑的人",
        "n": 1,
        "response_format": "b64_json",
        "extra_body": {"aspect_ratio": "16:9", "resolution": "1k"},
    }
    assert "size" not in client.images.request
    assert response.provider == "grok"
    assert response.images[0].base64_data == "Z3Jvaw=="
    assert response.images[0].mime_type == "image/webp"


@pytest.mark.asyncio
async def test_grok_single_reference_edit_uses_json_and_detects_aspect_ratio() -> None:
    client = FakeGrokClient()
    await grok_provider(client).generate_image(
        GenerateRequest(
            provider="grok",
            model="grok-imagine-image",
            prompt="增加自然光",
            aspect_ratio="16:9",
            resolution="2K",
        ),
        ReferenceImage(data=b"reference", content_type="image/jpeg", filename="room.jpg"),
    )

    path, kwargs = client.post_request
    assert path == "/images/edits"
    assert kwargs["body"] == {
        "model": "grok-imagine-image",
        "prompt": "增加自然光",
        "n": 1,
        "response_format": "b64_json",
        "aspect_ratio": "16:9",
        "resolution": "2k",
        "image": {"url": "data:image/jpeg;base64,cmVmZXJlbmNl"},
    }


@pytest.mark.asyncio
async def test_grok_multi_reference_edit_forwards_aspect_ratio() -> None:
    client = FakeGrokClient()
    await grok_provider(client).generate_image(
        GenerateRequest(
            provider="grok",
            model="grok-imagine-image",
            prompt="融合两张参考图",
            aspect_ratio="3:2",
            resolution="1K",
        ),
        [
            ReferenceImage(data=b"first", content_type="image/png"),
            ReferenceImage(data=b"second", content_type="image/webp"),
        ],
    )

    _, kwargs = client.post_request
    body = kwargs["body"]
    assert "image" not in body
    assert body["n"] == 1
    assert body["aspect_ratio"] == "3:2"
    assert body["resolution"] == "1k"
    assert body["images"] == [
        {"url": "data:image/png;base64,Zmlyc3Q="},
        {"url": "data:image/webp;base64,c2Vjb25k"},
    ]


@pytest.mark.asyncio
async def test_grok_forwards_native_count_up_to_ten() -> None:
    client = FakeGrokClient()
    await grok_provider(client).generate_image(
        GenerateRequest(
            provider="grok",
            model="grok-imagine-image",
            prompt="生成十张方案",
            count=10,
        )
    )

    assert client.images.request["n"] == 10


@pytest.mark.asyncio
async def test_grok_rejects_more_than_three_reference_images() -> None:
    references = [
        ReferenceImage(data=str(index).encode(), content_type="image/png")
        for index in range(4)
    ]

    with pytest.raises(ProviderRequestError) as raised:
        await grok_provider(FakeGrokClient()).generate_image(
            GenerateRequest(
                provider="grok",
                model="grok-imagine-image",
                prompt="融合参考图",
            ),
            references,
        )

    assert "at most 3 reference images" in raised.value.message


def test_grok_keeps_native_dimensions_and_limits_quality_by_model() -> None:
    request = GenerateRequest(
        provider="grok",
        model="grok-imagine-image",
        prompt="保持上游原图",
        count=4,
        detail="auto",
        size="16:9",
        aspect_ratio="16:9",
        resolution="2K",
    )

    normalized = normalize_generation_request(request)
    assert normalized.detail == "auto"
    assert normalized.size is None
    assert normalized.aspect_ratio == "16:9"
    assert normalized.resolution == "2K"
    quality_request = GenerateRequest(
        provider="grok",
        model="grok-imagine-image-2.0",
        prompt="高质量原图",
        detail="low",
        aspect_ratio="9:20",
        resolution="1K",
    )
    assert normalize_generation_request(quality_request).detail == "low"
    gpt_request = GenerateRequest(
        provider="openai",
        model="gpt-image-2",
        prompt="native batch",
        count=10,
    )
    assert gpt_request.count == 10


@pytest.mark.asyncio
async def test_grok_imagine_2_forwards_quality_and_defaults_to_medium() -> None:
    client = FakeGrokClient()
    request = GenerateRequest(
        provider="grok",
        model="grok-imagine-image-2.0",
        prompt="生成图片",
        aspect_ratio="auto",
        resolution="2K",
    )

    request = normalize_generation_request(request)
    await grok_provider(client).generate_image(request)

    assert request.detail == "medium"
    assert client.images.request["extra_body"] == {
        "aspect_ratio": "auto",
        "resolution": "2k",
        "quality": "medium",
    }


@pytest.mark.asyncio
async def test_grok_status_error_exposes_safe_upstream_reason() -> None:
    client = FakeGrokClient()
    request = httpx.Request("POST", "https://relay.example/v1/images/generations")
    response = httpx.Response(
        429,
        request=request,
        headers={"content-type": "application/json"},
        json={"error": {"message": "Grok quota exhausted for Bearer secret-token"}},
    )

    async def fail(**kwargs):
        raise openai.RateLimitError("rate limited", response=response, body=None)

    client.images.generate = fail

    with pytest.raises(ProviderRequestError) as raised:
        await grok_provider(client).generate_image(
            GenerateRequest(
                provider="grok",
                model="grok-imagine-image",
                prompt="test",
            )
        )

    assert raised.value.status_code == 429
    assert raised.value.message == (
        "Provider request failed (HTTP 429): "
        "Grok quota exhausted for Bearer [REDACTED]"
    )
