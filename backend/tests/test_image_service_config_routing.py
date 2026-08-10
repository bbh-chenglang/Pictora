from datetime import datetime
from types import SimpleNamespace

import pytest

from app.repositories.api_key_config_repository import ApiKeyConfigNotFoundError
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.image_service import ImageService


@pytest.mark.asyncio
async def test_image_service_routes_generation_by_owned_api_key_config():
    calls = []

    class Provider:
        provider_id = "gemini"

        async def generate_image(self, request):
            calls.append(request)
            return GenerateResponse(provider="gemini", model=request.model, images=[])

    class ConfigRepository:
        async def get_owned(self, user_id, config_id):
            assert user_id == 7
            assert config_id == 12
            return SimpleNamespace(
                id=12,
                user_id=7,
                alias="Gemini",
                api_key="secret",
                provider_type="gemini",
                model="gemini-image",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

    class Registry:
        def resolve(self, provider):
            raise AssertionError("legacy registry must not be used for configured generation")

    service = ImageService(
        Registry(), ConfigRepository(), user_id=7, provider_factory=lambda config: Provider()
    )
    response = await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-image",
            api_key_config_id=12,
            prompt="draw",
        ),
    )

    assert response.provider == "gemini"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_image_service_rejects_config_owned_by_another_user():
    class ConfigRepository:
        async def get_owned(self, user_id, config_id):
            return None

    service = ImageService(SimpleNamespace(), ConfigRepository(), user_id=7)

    with pytest.raises(ApiKeyConfigNotFoundError):
        await service.generate(
            GenerateRequest(
                provider="gemini",
                model="gemini-image",
                api_key_config_id=12,
                prompt="draw",
            )
        )


@pytest.mark.asyncio
async def test_image_service_routes_analysis_by_owned_api_key_config():
    calls = []

    class Provider:
        provider_id = "gemini"
        model = "gemini-image"

        async def analyze_image(self, model, prompt, image_bytes, content_type):
            calls.append((model, prompt, image_bytes, content_type))
            return SimpleNamespace(provider="gemini", model=model, text="分析完成")

    class ConfigRepository:
        async def get_owned(self, user_id, config_id):
            assert (user_id, config_id) == (7, 12)
            return SimpleNamespace(provider_type="gemini")

    class Registry:
        def resolve(self, provider):
            raise AssertionError("configured analysis must not use the legacy registry")

    service = ImageService(
        Registry(), ConfigRepository(), user_id=7, provider_factory=lambda config: Provider()
    )
    response = await service.analyze(
        "gemini",
        "gemini-image",
        "描述图片",
        "auto",
        b"image",
        "image/png",
        api_key_config_id=12,
    )

    assert response.text == "分析完成"
    assert calls == [("gemini-image", "描述图片", b"image", "image/png")]
