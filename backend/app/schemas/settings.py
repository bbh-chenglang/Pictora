from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.schemas.api_key_config import ApiKeyConfigSummary


class RuntimeProviderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=120)
    api_key: str | None = Field(default=None, max_length=500)


class RuntimeProviderSettingsResponse(BaseModel):
    provider_name: str
    model: str
    base_url: AnyHttpUrl
    provider_id: str = "compatible"
    api_key_configured: bool = False
    active_config_id: int | None = None
    configs: list[ApiKeyConfigSummary] = Field(default_factory=list)
