from functools import lru_cache
from pathlib import Path

from app.config import Settings
from app.providers.registry import ProviderRegistry
from app.services.image_service import ImageService


@lru_cache
def _get_settings(env_stamp: int) -> Settings:
    return Settings()


def _env_stamp() -> int:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    try:
        return env_file.stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def get_settings() -> Settings:
    return _get_settings(_env_stamp())


@lru_cache
def _get_provider_registry(env_stamp: int) -> ProviderRegistry:
    return ProviderRegistry.from_settings(get_settings())


def get_provider_registry() -> ProviderRegistry:
    return _get_provider_registry(_env_stamp())


@lru_cache
def _get_image_service(env_stamp: int) -> ImageService:
    return ImageService(get_provider_registry())


def get_image_service() -> ImageService:
    return _get_image_service(_env_stamp())


def clear_dependency_caches() -> None:
    """Clear settings and provider clients, primarily for tests and reloads."""
    _get_provider_registry.cache_clear()
    _get_image_service.cache_clear()
    _get_settings.cache_clear()
