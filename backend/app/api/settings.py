from fastapi import APIRouter, Depends, HTTPException, status
import httpx
from openai import APIError
from openai import AsyncOpenAI

from app.database import (
    FIXED_PROVIDER_NAME,
    GEMINI_BASE_URL,
    OPENAI_BASE_URL,
)
from app.providers.compatible_provider import COMPATIBLE_USER_AGENT
from app.dependencies import (
    clear_dependency_caches,
    get_api_key_config_repository,
    get_current_user,
    get_settings_repository,
)
from app.repositories.api_key_config_repository import (
    ApiKeyConfigAliasTakenError,
    ApiKeyConfigNotFoundError,
    ApiKeyConfigRepository,
)
from app.repositories.settings_repository import (
    SettingsRepository,
    StoredProviderSettings,
)
from app.schemas.settings import (
    RuntimeProviderSettings,
    RuntimeProviderSettingsResponse,
)
from app.schemas.api_key_config import (
    ActiveApiKeyConfigRequest,
    ApiKeyConfigCreate,
    ApiKeyConfigSummary,
    ApiKeyConfigUpdate,
    ApiKeyDiscoveryRequest,
    ApiKeyDiscoveryResponse,
    DiscoveredModel,
)
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/settings", tags=["settings"])

MODEL_BY_PROVIDER = {
    "gpt": "gpt-image-2",
    "gemini": "gemini-3.1-flash-image",
}


async def _list_openai_models(api_key: str) -> list[DiscoveredModel]:
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=OPENAI_BASE_URL,
        default_headers={"User-Agent": COMPATIBLE_USER_AGENT},
    )
    try:
        response = await client.models.list()
        return [
            DiscoveredModel(id=model_id, provider_type="gpt")
            for model in (getattr(response, "data", []) or [])
            if (model_id := getattr(model, "id", None))
        ]
    finally:
        await client.close()


async def _list_gemini_models(api_key: str) -> list[DiscoveredModel]:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        headers={
            "User-Agent": COMPATIBLE_USER_AGENT,
            "x-goog-api-key": api_key,
        },
    ) as client:
        response = await client.get(f"{GEMINI_BASE_URL}/models")
        response.raise_for_status()
        payload = response.json()
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return [
        DiscoveredModel(id=model_id, provider_type="gemini")
        for item in models
        if isinstance(item, dict)
        and isinstance((model_id := item.get("name")), str)
        and model_id
    ]


async def _list_remote_models(
    api_key: str, provider_type: str
) -> list[DiscoveredModel]:
    if provider_type == "gemini":
        return await _list_gemini_models(api_key)
    return await _list_openai_models(api_key)


def _summary(config) -> ApiKeyConfigSummary:
    return ApiKeyConfigSummary(
        id=config.id,
        alias=config.alias,
        provider_type=config.provider_type,
        model=config.model,
        api_key_configured=bool(config.api_key.strip()),
    )


async def _settings_response(repository: ApiKeyConfigRepository, user_id: int):
    configs = await repository.list_for_user(user_id)
    active_id = await repository.get_active_id(user_id)
    if active_id is None and configs:
        active_id = configs[0].id
    active = next((config for config in configs if config.id == active_id), configs[0] if configs else None)
    active_is_gemini = bool(active and active.provider_type == "gemini")
    return {
        "provider_name": FIXED_PROVIDER_NAME,
        "base_url": GEMINI_BASE_URL if active_is_gemini else OPENAI_BASE_URL,
        "provider_id": "gemini" if active_is_gemini else "compatible",
        "active_config_id": active_id,
        "model": active.model if active else MODEL_BY_PROVIDER["gpt"],
        "api_key_configured": bool(active and active.api_key.strip()),
        "configs": [_summary(config).model_dump() for config in configs],
    }


def _response(settings: StoredProviderSettings) -> dict[str, object]:
    return {
        "provider_name": settings.provider_name,
        "model": settings.model,
        "base_url": settings.base_url,
        "provider_id": "compatible",
        "api_key_configured": bool(settings.api_key.strip()),
    }


@router.get("", response_model=RuntimeProviderSettingsResponse)
async def read_settings(
    user: StoredSessionUser = Depends(get_current_user),
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
):
    return await _settings_response(repository, user.id)


@router.put("")
async def update_settings(
    request: RuntimeProviderSettings,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SettingsRepository = Depends(get_settings_repository),
) -> dict[str, object]:
    settings = await repository.update(user.id, request.model.strip(), request.api_key)
    clear_dependency_caches()
    return _response(settings)


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key_config(
    request: ApiKeyConfigCreate,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
):
    try:
        config = await repository.create(
            user.id, request.alias, request.api_key, request.provider_type, MODEL_BY_PROVIDER[request.provider_type]
        )
    except ApiKeyConfigAliasTakenError:
        raise HTTPException(409, {"error": {"code": "api_key_alias_taken", "message": "别名已存在"}}) from None
    return _summary(config)


@router.post("/api-keys/models", response_model=ApiKeyDiscoveryResponse)
async def discover_api_key_models(request: ApiKeyDiscoveryRequest) -> ApiKeyDiscoveryResponse:
    try:
        return ApiKeyDiscoveryResponse(
            models=await _list_remote_models(request.api_key.strip(), request.provider_type)
        )
    except (APIError, httpx.HTTPError, ValueError):
        raise HTTPException(502, {"error": {"code": "api_key_model_discovery_failed", "message": "无法获取模型列表"}}) from None


@router.get("/api-keys/{config_id}/models", response_model=ApiKeyDiscoveryResponse)
async def list_api_key_config_models(
    config_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
) -> ApiKeyDiscoveryResponse:
    config = await repository.get_owned(user.id, config_id)
    if config is None:
        raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}})
    try:
        models = await _list_remote_models(config.api_key, config.provider_type)
    except (APIError, httpx.HTTPError, ValueError):
        raise HTTPException(502, {"error": {"code": "api_key_model_discovery_failed", "message": "无法获取模型列表"}}) from None
    return ApiKeyDiscoveryResponse(
        models=[model for model in models if model.provider_type == config.provider_type]
    )


@router.post("/api-keys/{config_id}/test")
async def test_api_key_config(
    config_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
):
    config = await repository.get_owned(user.id, config_id)
    if config is None:
        raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}})
    try:
        models = await _list_remote_models(config.api_key, config.provider_type)
    except (APIError, httpx.HTTPError, ValueError):
        return {"available": False, "message": "API Key 不可用"}
    available = bool(models)
    return {
        "available": available,
        "message": "API Key 可用" if available else "API Key 不可用",
        "models": [model.model_dump() for model in models],
    }


@router.patch("/api-keys/{config_id}")
async def update_api_key_config(
    config_id: int,
    request: ApiKeyConfigUpdate,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
):
    try:
        current = await repository.get_owned(user.id, config_id)
        if current is None:
            raise ApiKeyConfigNotFoundError(config_id)
        changes = request.model_dump(exclude_unset=True)
        provider_type = changes.get("provider_type", current.provider_type)
        if provider_type != current.provider_type and "model" not in changes:
            changes["model"] = MODEL_BY_PROVIDER[provider_type]
        config = await repository.update(
            user.id,
            config_id,
            **changes,
        )
    except ApiKeyConfigNotFoundError:
        raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}}) from None
    except ApiKeyConfigAliasTakenError:
        raise HTTPException(409, {"error": {"code": "api_key_alias_taken", "message": "别名已存在"}}) from None
    return _summary(config)


@router.delete("/api-keys/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key_config(
    config_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
) -> None:
    try:
        await repository.delete(user.id, config_id)
    except ApiKeyConfigNotFoundError:
        raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}}) from None


@router.put("/active")
async def activate_api_key_config(
    request: ActiveApiKeyConfigRequest,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ApiKeyConfigRepository = Depends(get_api_key_config_repository),
):
    try:
        config = await repository.set_active(user.id, request.config_id)
    except ApiKeyConfigNotFoundError:
        raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}}) from None
    return {"active_config_id": config.id}
