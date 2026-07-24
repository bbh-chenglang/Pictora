from pydantic import AnyHttpUrl, BaseModel, Field


class RuntimeProviderSettings(BaseModel):
    provider_name: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    base_url: AnyHttpUrl
    api_key: str | None = Field(default=None, min_length=1, max_length=500)


class RuntimeProviderSettingsResponse(BaseModel):
    provider_name: str
    model: str
    base_url: AnyHttpUrl
    provider_id: str = "compatible"
    api_key_configured: bool = False
