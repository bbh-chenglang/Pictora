import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.providers.compatible_provider import COMPATIBLE_USER_AGENT
from app.providers.gemini_provider import GeminiProvider
from app.schemas.generate import GenerateRequest, ReferenceImage


def test_gemini_model_capabilities_normalize_native_image_parameters():
    modern = GenerateRequest(
        provider="gemini",
        model="gemini-3.1-flash-image",
        prompt="wide panorama",
        aspect_ratio="1:8",
        resolution="4K",
    )
    legacy = GenerateRequest(
        provider="gemini",
        model="gemini-2.5-flash-image",
        prompt="square image",
        aspect_ratio="1:1",
        resolution="4K",
    )
    lite = GenerateRequest(
        provider="gemini",
        model="gemini-3.1-flash-lite-image-preview",
        prompt="square image",
        resolution="2K",
    )

    assert modern.aspect_ratio == "1:8"
    assert modern.resolution == "4K"
    assert legacy.resolution is None
    assert lite.resolution is None
    with pytest.raises(ValidationError):
        GenerateRequest(
            provider="gemini",
            model="gemini-3-pro-image-preview",
            prompt="unsupported extreme ratio",
            aspect_ratio="8:1",
        )
    with pytest.raises(ValidationError):
        GenerateRequest(
            provider="gemini",
            model="gemini-3.1-flash-image",
            prompt="Grok-only ratio",
            aspect_ratio="20:9",
        )


def test_gpt_native_format_and_background_constraints():
    request = GenerateRequest(
        provider="openai",
        model="gpt-image-1.5",
        prompt="transparent asset",
        output_format="webp",
        background="transparent",
        output_compression=77,
    )
    png = GenerateRequest(
        provider="openai",
        model="gpt-image-1.5",
        prompt="lossless asset",
        output_format="png",
        output_compression=77,
    )

    assert request.output_compression == 77
    assert png.output_compression is None
    with pytest.raises(ValidationError):
        GenerateRequest(
            provider="openai",
            model="gpt-image-2",
            prompt="unsupported transparent background",
            output_format="png",
            background="transparent",
        )


def test_gemini_provider_uses_native_gateway_headers(monkeypatch):
    arguments = {}

    class FakeClient:
        def __init__(self, **kwargs):
            arguments.update(kwargs)

    monkeypatch.setattr("app.providers.gemini_provider.httpx.AsyncClient", FakeClient)

    GeminiProvider(
        api_key=SecretStr("secret"),
        base_url="https://sub.beibeihai.xyz/v1beta",
        model="gemini-3.1-flash-image",
    )

    assert arguments["headers"] == {
        "User-Agent": COMPATIBLE_USER_AGENT,
        "x-goog-api-key": "secret",
    }
    assert arguments["timeout"].read == 300.0


@pytest.mark.asyncio
async def test_gemini_provider_sends_native_image_config_and_extracts_inline_data():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "generated"},
                                {
                                    "inlineData": {
                                        "mimeType": "image/jpeg",
                                        "data": "YWJj",
                                    }
                                },
                            ]
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"x-goog-api-key": "secret"},
    ) as client:
        provider = GeminiProvider(
            api_key=SecretStr("secret"),
            base_url="https://sub.beibeihai.xyz/v1beta",
            model="gemini-3.1-flash-image",
            client=client,
        )
        response = await provider.generate_image(
            GenerateRequest(
                provider="gemini",
                model="gemini-3.1-flash-image",
                prompt="生成两只小猫",
                aspect_ratio="16:9",
                resolution="4K",
            )
        )

    assert response.images[0].base64_data == "data:image/jpeg;base64,YWJj"
    request = captured["request"]
    assert str(request.url) == (
        "https://sub.beibeihai.xyz/v1beta/models/"
        "gemini-3.1-flash-image:generateContent"
    )
    assert json.loads(request.content) == {
        "contents": [
            {"role": "user", "parts": [{"text": "生成两只小猫"}]}
        ],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": "16:9", "imageSize": "4K"},
        },
    }


@pytest.mark.asyncio
async def test_gemini_provider_combines_reference_image_with_prompt():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(
            api_key="secret",
            base_url="https://sub.beibeihai.xyz/v1beta",
            model="gemini-3.1-flash-image",
            client=client,
        )
        await provider.generate_image(
            GenerateRequest(
                provider="gemini",
                model="gemini-3.1-flash-image",
                prompt="保持空间结构，改成暖色自然光",
                aspect_ratio="16:9",
                resolution="4K",
            ),
            ReferenceImage(
                data=b"reference-bytes",
                content_type="image/jpeg",
                filename="room.jpg",
            ),
        )

    assert captured["body"]["contents"][0]["parts"] == [
        {"text": "保持空间结构，改成暖色自然光"},
        {
            "inlineData": {
                "mimeType": "image/jpeg",
                "data": "cmVmZXJlbmNlLWJ5dGVz",
            }
        },
    ]


@pytest.mark.asyncio
async def test_gemini_provider_combines_multiple_reference_images_with_prompt():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"candidates": []})

    references = [
        ReferenceImage(data=b"room", content_type="image/jpeg", filename="room.jpg"),
        ReferenceImage(data=b"material", content_type="image/png", filename="material.png"),
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(
            api_key="secret",
            base_url="https://sub.beibeihai.xyz/v1beta",
            model="gemini-3.1-flash-image",
            client=client,
        )
        await provider.generate_image(
            GenerateRequest(
                provider="gemini",
                model="gemini-3.1-flash-image",
                prompt="融合空间和材质",
            ),
            references,
        )

    assert captured["body"]["contents"][0]["parts"] == [
        {"text": "融合空间和材质"},
        {"inlineData": {"mimeType": "image/jpeg", "data": "cm9vbQ=="}},
        {"inlineData": {"mimeType": "image/png", "data": "bWF0ZXJpYWw="}},
    ]


@pytest.mark.asyncio
async def test_gemini_provider_analyzes_images_through_native_endpoint():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "一张测试图片"}]}}
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GeminiProvider(
            api_key="secret",
            base_url="https://sub.beibeihai.xyz/v1beta",
            model="models/gemini-image",
            client=client,
        )
        response = await provider.analyze_image(
            "models/gemini-image", "描述图片", b"abc", "image/png"
        )

    assert response.text == "一张测试图片"
    assert captured["body"]["contents"][0]["parts"] == [
        {"text": "描述图片"},
        {"inlineData": {"mimeType": "image/png", "data": "YWJj"}},
    ]
