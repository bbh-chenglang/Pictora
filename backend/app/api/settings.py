from fastapi import APIRouter, Depends

from app.dependencies import get_settings, update_runtime_provider_settings
from app.schemas.settings import RuntimeProviderSettings, RuntimeProviderSettingsResponse

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _response(settings) -> RuntimeProviderSettingsResponse:
    return RuntimeProviderSettingsResponse(
        provider_name=settings.custom_provider_name,
        model=settings.custom_model,
        base_url=settings.custom_base_url,
        api_key_configured=bool(settings.custom_api_key.get_secret_value().strip()),
    )


@router.get("", response_model=RuntimeProviderSettingsResponse)
async def read_settings(settings=Depends(get_settings)):
    return _response(settings)


@router.put("", response_model=RuntimeProviderSettingsResponse)
async def update_settings(request: RuntimeProviderSettings):
    settings = update_runtime_provider_settings(
        request.provider_name,
        request.model,
        str(request.base_url).rstrip("/"),
        request.api_key,
    )
    return _response(settings)
