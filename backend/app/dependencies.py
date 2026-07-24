from functools import lru_cache

from fastapi import Depends

from app.config import Settings
from app.providers.registry import ProviderRegistry


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_provider_registry(settings: Settings = Depends(get_settings)) -> ProviderRegistry:
    return ProviderRegistry.from_settings(settings)
