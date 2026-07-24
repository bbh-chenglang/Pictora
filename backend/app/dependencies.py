from functools import lru_cache

from app.config import Settings
from app.providers.registry import ProviderRegistry
from app.services.image_service import ImageService


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    return ProviderRegistry.from_settings(get_settings())


@lru_cache
def get_image_service() -> ImageService:
    return ImageService(get_provider_registry())


def clear_dependency_caches() -> None:
    """Clear settings and provider clients, primarily for tests and reloads."""
    get_provider_registry.cache_clear()
    get_image_service.cache_clear()
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
