from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.config import Settings
import app.dependencies as dependencies
from app.providers.base import ProviderNotFoundError
from app.providers.compatible_provider import CompatibleProvider
from app.providers.custom_provider import CustomProvider
from app.providers.registry import ProviderRegistry


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
        custom_base_url="http://localhost:11434/v1",
        custom_model="local-image-model",
    )

    registry = ProviderRegistry.from_settings(settings)

    provider = registry.resolve("compatible")
    assert isinstance(provider, CompatibleProvider)
    assert provider.model == "local-image-model"
    assert [item.models for item in registry.list_models()] == [["local-image-model"]]
    assert "custom-secret" not in repr(registry.list_models())


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


def test_registry_dependency_reuses_clients_until_cache_is_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        openai_api_key=SecretStr("openai-secret"),
        custom_api_key=SecretStr(""),
    )
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    dependencies.clear_dependency_caches()

    try:
        first = dependencies.get_provider_registry()
        second = dependencies.get_provider_registry()

        assert first is second
        assert first.resolve("openai").client is second.resolve("openai").client

        dependencies.clear_dependency_caches()
        third = dependencies.get_provider_registry()
        assert third is not first
        assert third.resolve("openai").client is not first.resolve("openai").client
    finally:
        dependencies.clear_dependency_caches()
