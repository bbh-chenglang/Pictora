from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.config import Settings
import app.dependencies as dependencies
from app.providers.base import ProviderNotFoundError
from app.providers.compatible_provider import CompatibleProvider
from app.providers.custom_provider import CustomProvider
from app.providers.registry import ProviderRegistry
from app.repositories.settings_repository import StoredProviderSettings


def test_registry_registers_only_providers_with_non_empty_keys() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key=SecretStr("openai-secret"),
        custom_api_key=SecretStr(""),
    )

    registry = ProviderRegistry.from_settings(settings)

    assert registry.resolve("openai").model == settings.openai_model
    with pytest.raises(ProviderNotFoundError):
        registry.resolve("compatible")
    assert [item.id for item in registry.list_models()] == ["openai"]
    assert "secret" not in repr(registry.list_models()).lower()


def test_registry_uses_custom_key_for_compatible_provider_without_exposing_it() -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key=SecretStr(""),
        custom_api_key=SecretStr("custom-secret"),
        custom_provider_name="我的图像服务",
        custom_base_url="http://localhost:11434/v1",
        custom_model="local-image-model",
    )

    registry = ProviderRegistry.from_settings(settings)

    provider = registry.resolve("compatible")
    assert isinstance(provider, CompatibleProvider)
    assert provider.model == "local-image-model"
    assert provider.label == "我的图像服务"
    assert [item.models for item in registry.list_models()] == [["local-image-model"]]
    assert "custom-secret" not in repr(registry.list_models())


def test_registry_builds_fixed_compatible_provider_from_stored_settings() -> None:
    registry = ProviderRegistry.from_stored_settings(
        StoredProviderSettings(
            provider_name="北海AI",
            base_url="https://sub.beibeihai.xyz/v1",
            model="custom-image-model",
            api_key="stored-secret",
        )
    )

    provider = registry.resolve("compatible")

    assert provider.label == "北海AI"
    assert provider.model == "custom-image-model"
    assert [item.id for item in registry.list_models()] == ["compatible"]
    assert "stored-secret" not in repr(registry.list_models())


@pytest.mark.asyncio
async def test_compatible_provider_uses_browser_user_agent() -> None:
    provider = CompatibleProvider(
        api_key=SecretStr("stored-secret"),
        base_url="https://sub.beibeihai.xyz/v1",
        model="gpt-image-2",
    )

    try:
        user_agent = provider.client.default_headers["User-Agent"]
        assert user_agent.startswith("Mozilla/5.0")
        assert "OpenAI/Python" not in user_agent
    finally:
        await provider.client.close()


@pytest.mark.asyncio
async def test_custom_provider_fails_explicitly() -> None:
    provider = CustomProvider()

    with pytest.raises(Exception) as error:
        await provider.generate_image(
            SimpleNamespace(provider="custom", model="x", prompt="draw", detail="auto")
        )

    assert error.value.code == "provider_not_implemented"

    with pytest.raises(Exception) as error:
        await provider.analyze_image("x", "describe", b"bytes", "image/png")

    assert error.value.code == "provider_not_implemented"


@pytest.mark.asyncio
async def test_registry_dependency_reuses_clients_until_cache_is_cleared() -> None:
    settings = StoredProviderSettings(
        provider_name="北海AI",
        base_url="https://sub.beibeihai.xyz/v1",
        model="custom-image-model",
        api_key="stored-secret",
    )

    class Repository:
        async def get(self):
            return settings

    repository = Repository()
    dependencies.clear_dependency_caches()

    try:
        first = await dependencies.get_provider_registry(repository)
        second = await dependencies.get_provider_registry(repository)

        assert first is second
        assert first.resolve("compatible").client is second.resolve("compatible").client

        dependencies.clear_dependency_caches()
        third = await dependencies.get_provider_registry(repository)
        assert third is not first
        assert third.resolve("compatible").client is not first.resolve("compatible").client
    finally:
        dependencies.clear_dependency_caches()
