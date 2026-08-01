from fastapi import APIRouter, Depends

from app.dependencies import clear_dependency_caches, get_current_user, get_settings_repository
from app.repositories.settings_repository import (
    SettingsRepository,
    StoredProviderSettings,
)
from app.schemas.settings import (
    RuntimeProviderSettings,
    RuntimeProviderSettingsResponse,
)
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _response(settings: StoredProviderSettings) -> RuntimeProviderSettingsResponse:
    return RuntimeProviderSettingsResponse(
        provider_name=settings.provider_name,
        model=settings.model,
        base_url=settings.base_url,
        api_key_configured=bool(settings.api_key.strip()),
    )


@router.get("", response_model=RuntimeProviderSettingsResponse)
async def read_settings(
    user: StoredSessionUser = Depends(get_current_user),
    repository: SettingsRepository = Depends(get_settings_repository),
) -> RuntimeProviderSettingsResponse:
    return _response(await repository.get(user.id))


@router.put("", response_model=RuntimeProviderSettingsResponse)
async def update_settings(
    request: RuntimeProviderSettings,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SettingsRepository = Depends(get_settings_repository),
) -> RuntimeProviderSettingsResponse:
    settings = await repository.update(user.id, request.model.strip(), request.api_key)
    clear_dependency_caches()
    return _response(settings)
