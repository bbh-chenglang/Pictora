from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


PromptCategory = str
MAX_PROMPT_CATEGORY_LENGTH = 40


def normalize_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("内容不能为空")
    return normalized


def normalize_category(value: str | None) -> str:
    return (value or "").strip()


class PromptCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=4000)
    category: PromptCategory = Field(default="", max_length=MAX_PROMPT_CATEGORY_LENGTH)

    _normalize_text = field_validator("name", "prompt")(normalize_text)
    _normalize_category = field_validator("category", mode="before")(normalize_category)


class PromptUpdateRequest(PromptCreateRequest):
    pass


class PromptSummary(BaseModel):
    id: int
    user_id: int
    name: str
    prompt: str
    category: PromptCategory
    created_at: datetime
    updated_at: datetime
