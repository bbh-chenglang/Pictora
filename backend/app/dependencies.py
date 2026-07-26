from functools import lru_cache

from fastapi import Depends

from app.database import (
    DATABASE_PATH,
    FIXED_BASE_URL,
    FIXED_PROVIDER_NAME,
)
from app.providers.registry import ProviderRegistry
from app.repositories.settings_repository import (
    SettingsRepository,
    StoredProviderSettings,
)
from app.repositories.history_repository import HistoryRepository
from app.services.history_service import HistoryService
from app.services.image_service import ImageService


@lru_cache
def get_settings_repository() -> SettingsRepository:
    return SettingsRepository(DATABASE_PATH)


@lru_cache
def get_history_repository() -> HistoryRepository:
    return HistoryRepository(DATABASE_PATH)


@lru_cache
def _registry_for(api_key: str, model: str) -> ProviderRegistry:
    return ProviderRegistry.from_stored_settings(
        StoredProviderSettings(
            provider_name=FIXED_PROVIDER_NAME,
            base_url=FIXED_BASE_URL,
            model=model,
            api_key=api_key,
        )
    )


async def get_provider_registry(
    repository: SettingsRepository = Depends(get_settings_repository),
) -> ProviderRegistry:
    settings = await repository.get()
    return _registry_for(settings.api_key, settings.model)


async def get_image_service(
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> ImageService:
    return ImageService(registry)


def get_history_service(
    repository: HistoryRepository = Depends(get_history_repository),
) -> HistoryService:
    return HistoryService(repository)


def clear_dependency_caches() -> None:
    _registry_for.cache_clear()
    get_settings_repository.cache_clear()
    get_history_repository.cache_clear()
