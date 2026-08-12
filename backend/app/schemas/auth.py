from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    email: str
    verification_code: str = Field(pattern=r"^\d{6}$")
    password: str = Field(min_length=6)
    password_confirmation: str = Field(min_length=6)

    @field_validator("username")
    @classmethod
    def username_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("用户名不能为空")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized) is None:
            raise ValueError("请输入有效邮箱")
        return normalized

    @field_validator("password_confirmation")
    @classmethod
    def passwords_must_match(cls, value: str, info) -> str:
        if info.data.get("password") != value:
            raise ValueError("两次密码输入不一致")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_login_identifier(cls, value: str) -> str:
        return value.strip().lower()


class VerificationCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized) is None:
            raise ValueError("请输入有效邮箱")
        return normalized


class VerificationCodeResponse(BaseModel):
    message: str
    retry_after_seconds: int


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


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str

    @field_validator("username")
    @classmethod
    def username_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("用户名不能为空")
        return normalized


class CurrentUserResponse(BaseModel):
    username: str
    email: str | None
    is_admin: bool
    api_key_configured: bool


class StoredUser(BaseModel):
    id: int
    username: str
    email: str | None = None
    email_verified_at: datetime | None = None
    is_admin: bool = False
    password_hash: str
    api_key: str
    model: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None
    last_activity_at: datetime | None = None


class StoredSessionUser(BaseModel):
    id: int
    username: str
    email: str | None = "test@example.com"
    is_admin: bool = False
    api_key: str
    model: str
