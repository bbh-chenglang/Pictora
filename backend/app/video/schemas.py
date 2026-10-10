from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

MaterialType = Literal["image", "video", "audio"]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class VideoKeyCreate(StrictModel):
    alias: str = Field(min_length=1, max_length=80)
    api_key: SecretStr
    model: str = "seedance-2.0-933-720P（秒）"

    @field_validator("alias", "model")
    @classmethod
    def trim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value.strip()

    @field_validator("api_key")
    @classmethod
    def nonempty_key(cls, value: SecretStr) -> SecretStr:
        key = value.get_secret_value().strip()
        if not key or len(key) > 500:
            raise ValueError("无效的 API Key")
        return SecretStr(key)

class VideoKeyUpdate(StrictModel):
    alias: str | None = Field(default=None, min_length=1, max_length=80)
    api_key: SecretStr | None = None
    model: str | None = None

    @field_validator("alias", "model")
    @classmethod
    def trim(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("不能为空")
        return value.strip() if value else value

    _validate_key = field_validator("api_key")(lambda v: VideoKeyCreate.nonempty_key(v) if v is not None else v)

class VideoMaterial(StrictModel):
    type: MaterialType
    name: str = Field(default="", max_length=80)
    asset_id: str | None = None
    url: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def exactly_one_source(self):
        if bool(self.asset_id) == bool(self.url):
            raise ValueError("每个素材必须提供一个素材 ID 或 HTTPS 链接")
        self.name = self.name.strip()
        return self

class VideoTaskCreate(StrictModel):
    request_id: UUID
    project_id: int = Field(gt=0)
    api_key_config_id: int = Field(gt=0)
    model: str = Field(default="seedance-2.0-933-720P（秒）", min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=20000)
    duration: int | None = Field(default=None, gt=0, strict=True)
    resolution: str | None = None
    ratio: str | None = None
    materials: list[VideoMaterial] = Field(default_factory=list, max_length=50)

    @field_validator("prompt")
    @classmethod
    def trim_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("提示词不能为空")
        return value.strip()

class VideoKeySelection(StrictModel):
    config_id: int = Field(gt=0)

class HistoryImageSource(StrictModel):
    history_id: int = Field(gt=0)
    image_id: int = Field(gt=0)
    name: str = Field(default="", max_length=80)

class BindUpstreamTask(StrictModel):
    upstream_task_id: str = Field(min_length=1, max_length=256)

ACTIVE_STATUSES = ("queued", "submitting", "running", "saving")
TRACKED_STATUSES = (*ACTIVE_STATUSES, "polling_paused", "submission_unknown", "storage_failed")

