from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str = Field(min_length=6)
    password_confirmation: str = Field(min_length=6)

    @field_validator("username")
    @classmethod
    def username_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("用户名不能为空")
        return value

    @field_validator("password_confirmation")
    @classmethod
    def passwords_must_match(cls, value: str, info) -> str:
        if info.data.get("password") != value:
            raise ValueError("两次密码输入不一致")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    old_password: str
    new_password: str = Field(min_length=6)
    new_password_confirmation: str = Field(min_length=6)

    @field_validator("new_password_confirmation")
    @classmethod
    def new_passwords_must_match(cls, value: str, info) -> str:
        if info.data.get("new_password") != value:
            raise ValueError("两次新密码输入不一致")
        return value


class CurrentUserResponse(BaseModel):
    username: str
    api_key_configured: bool


class StoredUser(BaseModel):
    id: int
    username: str
    password_hash: str
    api_key: str
    model: str
    created_at: datetime
    updated_at: datetime


class StoredSessionUser(BaseModel):
    id: int
    username: str
    api_key: str
    model: str
