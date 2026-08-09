from functools import lru_cache

from fastapi import Cookie, Depends, HTTPException

from app.auth import SESSION_COOKIE, hash_session_token
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
from app.repositories.api_key_config_repository import ApiKeyConfigRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import StoredSessionUser
from app.services.history_service import HistoryService
from app.services.image_service import ImageService


@lru_cache
def get_settings_repository() -> SettingsRepository:
    return SettingsRepository(DATABASE_PATH)


@lru_cache
def get_api_key_config_repository() -> ApiKeyConfigRepository:
    return ApiKeyConfigRepository(DATABASE_PATH)


@lru_cache
def get_history_repository() -> HistoryRepository:
    return HistoryRepository(DATABASE_PATH)


@lru_cache
def get_project_repository() -> ProjectRepository:
    return ProjectRepository(DATABASE_PATH)


@lru_cache
def get_user_repository() -> UserRepository:
    return UserRepository(DATABASE_PATH)


async def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    repository: UserRepository = Depends(get_user_repository),
) -> StoredSessionUser:
    if not session_token:
        raise HTTPException(
            401,
            {"error": {"code": "authentication_required", "message": "请先登录"}},
        )
    user = await repository.get_session_user(hash_session_token(session_token))
    if user is None:
        raise HTTPException(
            401,
            {"error": {"code": "authentication_required", "message": "请先登录"}},
        )
    return user


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
    user: StoredSessionUser = Depends(get_current_user),
    repository: SettingsRepository = Depends(get_settings_repository),
) -> ProviderRegistry:
    settings = await repository.get(user.id)
    return _registry_for(settings.api_key, settings.model)


async def get_image_service(
    registry: ProviderRegistry = Depends(get_provider_registry),
) -> ImageService:
    return ImageService(registry)


def get_history_service(
    repository: HistoryRepository = Depends(get_history_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> HistoryService:
    return HistoryService(repository, project_repository=project_repository)


def clear_dependency_caches() -> None:
    _registry_for.cache_clear()
    get_settings_repository.cache_clear()
    get_api_key_config_repository.cache_clear()
    get_history_repository.cache_clear()
    get_project_repository.cache_clear()
    get_user_repository.cache_clear()
