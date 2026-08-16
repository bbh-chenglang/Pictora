from functools import lru_cache

from fastapi import Cookie, Depends, HTTPException

from app.auth import SESSION_COOKIE, hash_session_token
from app.config import Settings
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
from app.repositories.admin_repository import AdminRepository
from app.repositories.skill_repository import SkillRepository
from app.repositories.prompt_repository import PromptRepository
from app.repositories.verification_code_repository import VerificationCodeRepository
from app.schemas.auth import StoredSessionUser
from app.services.email_sender import EmailSender
from app.services.history_service import HistoryService
from app.services.image_service import ImageService
from app.services.generation_task_manager import GenerationTaskManager
from app.services.auth_rate_limiter import AuthRateLimiter


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


@lru_cache
def get_verification_code_repository() -> VerificationCodeRepository:
    return VerificationCodeRepository(DATABASE_PATH)


@lru_cache
def get_admin_repository() -> AdminRepository:
    return AdminRepository(DATABASE_PATH)


@lru_cache
def get_skill_repository() -> SkillRepository:
    return SkillRepository(DATABASE_PATH)


@lru_cache
def get_prompt_repository() -> PromptRepository:
    return PromptRepository(DATABASE_PATH)


@lru_cache
def get_email_sender() -> EmailSender:
    return EmailSender(Settings())


@lru_cache
def get_auth_rate_limiter() -> AuthRateLimiter:
    settings = Settings()
    return AuthRateLimiter(
        login_max_failures=settings.auth_login_max_failures,
        login_window_seconds=settings.auth_login_window_seconds,
        verification_max_requests_per_ip=settings.auth_verification_max_requests_per_ip,
        verification_global_max_requests=settings.auth_verification_global_max_requests,
        verification_window_seconds=settings.auth_verification_window_seconds,
    )


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
    should_be_admin = bool(
        user.email and user.email.lower() in Settings().admin_email_set
    )
    if user.is_admin != should_be_admin:
        await repository.set_admin(user.id, should_be_admin)
        user = user.model_copy(update={"is_admin": should_be_admin})
    await repository.touch_activity(user.id)
    return user


async def get_current_admin(
    user: StoredSessionUser = Depends(get_current_user),
) -> StoredSessionUser:
    if not user.is_admin:
        raise HTTPException(
            403,
            {"error": {"code": "admin_required", "message": "需要管理员权限"}},
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
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
    user: StoredSessionUser = Depends(get_current_user),
) -> ImageService:
    return ImageService(registry, repository, user.id)


def get_history_service(
    repository: HistoryRepository = Depends(get_history_repository),
    project_repository: ProjectRepository = Depends(get_project_repository),
) -> HistoryService:
    return HistoryService(repository, project_repository=project_repository)


@lru_cache
def get_generation_task_manager() -> GenerationTaskManager:
    settings = Settings()
    return GenerationTaskManager(
        max_concurrency=settings.generation_max_concurrency,
        max_active_tasks=settings.generation_max_active_tasks,
        max_tasks_per_user=settings.generation_max_tasks_per_user,
    )


def clear_dependency_caches() -> None:
    _registry_for.cache_clear()
    get_settings_repository.cache_clear()
    get_api_key_config_repository.cache_clear()
    get_history_repository.cache_clear()
    get_project_repository.cache_clear()
    get_user_repository.cache_clear()
    get_verification_code_repository.cache_clear()
    get_admin_repository.cache_clear()
    get_skill_repository.cache_clear()
    get_prompt_repository.cache_clear()
    get_email_sender.cache_clear()
    get_auth_rate_limiter.cache_clear()
