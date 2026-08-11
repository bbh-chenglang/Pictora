from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminUserSummary(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool
    password_status: str = "bcrypt 已加密"
    created_at: datetime
    last_login_at: datetime | None = None
    last_activity_at: datetime | None = None
    last_used_at: datetime | None = None
    usage_count: int
    generation_count: int
    analysis_count: int
    total_elapsed_ms: int
    models_used: list[str]


class AdminUsageRecord(BaseModel):
    id: int
    kind: str
    status: str
    provider: str
    model: str
    detail: str
    image_count: int
    size: str | None = None
    resolution: str | None = None
    elapsed_ms: int | None = None
    created_at: datetime
    completed_at: datetime | None = None


class AdminPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    new_password: str = Field(min_length=8)
