from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


@dataclass(frozen=True)
class StoredApiKeyConfig:
    id: int
    user_id: int
    alias: str
    api_key: str
    provider_type: str
    model: str
    created_at: datetime
    updated_at: datetime


ProviderType = Literal["gpt", "gemini"]


class ApiKeyConfigCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=80)
    api_key: str = Field(default="", max_length=500)
    provider_type: ProviderType
    model: str = Field(min_length=1, max_length=120)

    @field_validator("alias", "model")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value


class ApiKeyConfigUpdate(BaseModel):
    alias: str | None = Field(default=None, min_length=1, max_length=80)
    api_key: str | None = Field(default=None, max_length=500)
    provider_type: ProviderType | None = None
    model: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("alias", "model")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("value cannot be blank")
        return value


class ApiKeyConfigSummary(BaseModel):
    id: int
    alias: str
    provider_type: ProviderType
    model: str
    api_key_configured: bool


class ActiveApiKeyConfigRequest(BaseModel):
    config_id: int = Field(gt=0)
