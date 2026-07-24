from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.config import Settings
from app.providers.registry import ProviderRegistry
from app.services.image_service import ImageService

_runtime_overrides: dict[str, Any] = {}
_runtime_revision = 0


@lru_cache
def _get_settings(env_stamp: int, runtime_revision: int) -> Settings:
    settings = Settings()
    if _runtime_overrides:
        settings = settings.model_copy(update=_runtime_overrides)
    return settings


def _env_stamp() -> int:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    try:
        return env_file.stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def get_settings() -> Settings:
    return _get_settings(_env_stamp(), _runtime_revision)


@lru_cache
def _get_provider_registry(env_stamp: int, runtime_revision: int) -> ProviderRegistry:
    return ProviderRegistry.from_settings(get_settings())


def get_provider_registry() -> ProviderRegistry:
    return _get_provider_registry(_env_stamp(), _runtime_revision)


@lru_cache
def _get_image_service(env_stamp: int, runtime_revision: int) -> ImageService:
    return ImageService(get_provider_registry())


def get_image_service() -> ImageService:
    return _get_image_service(_env_stamp(), _runtime_revision)


def update_runtime_provider_settings(
    provider_name: str,
    model: str,
    base_url: str,
    api_key: str | None = None,
) -> Settings:
    global _runtime_revision
    _runtime_overrides.update(
        {
            "custom_provider_name": provider_name,
            "custom_model": model,
            "custom_base_url": base_url,
        }
    )
    if api_key is not None:
        _runtime_overrides["custom_api_key"] = SecretStr(api_key)
    _runtime_revision += 1
    clear_dependency_caches()
    return get_settings()


def clear_dependency_caches() -> None:
    """Clear settings and provider clients, primarily for tests and reloads."""
    _get_provider_registry.cache_clear()
    _get_image_service.cache_clear()
    _get_settings.cache_clear()
