from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SkillCategory = Literal["portrait", "product", "marketing", "illustration", "other"]
SkillStatus = Literal["draft", "pending", "published", "rejected"]
ReferenceCategory = Literal["person", "environment", "object"]


class SkillCustomView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=40)


class SkillMultiView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    target: Literal["person", "object"] = "person"
    preset_keys: list[str] = Field(default_factory=list, max_length=8)
    custom_views: list[SkillCustomView] = Field(default_factory=list, max_length=8)


class SkillWorkflow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_template: str = Field(min_length=1, max_length=4000)
    provider_type: Literal["gpt", "gemini", "grok"]
    model: str = Field(min_length=1, max_length=200)
    quality: str = Field(default="auto", max_length=40)
    size: str = Field(default="", max_length=40)
    resolution: str = Field(default="", max_length=40)
    image_count: int = Field(default=1, ge=1, le=10)
    reference_requirements: list[ReferenceCategory] = Field(default_factory=list, max_length=3)
    multi_view: SkillMultiView = Field(default_factory=SkillMultiView)

    @field_validator("reference_requirements")
    @classmethod
    def unique_reference_requirements(
        cls, value: list[ReferenceCategory]
    ) -> list[ReferenceCategory]:
        return list(dict.fromkeys(value))


class SkillCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=600)
    category: SkillCategory
    workflow: SkillWorkflow

    @field_validator("title", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("内容不能为空")
        return normalized


class SkillSummary(BaseModel):
    id: int
    author_id: int
    author_name: str
    title: str
    description: str
    category: SkillCategory
    status: SkillStatus
    workflow: SkillWorkflow
    has_cover: bool
    is_favorited: bool
    favorite_count: int
    use_count: int
    moderation_note: str | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class SkillReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["published", "rejected"]
    note: str = Field(default="", max_length=500)

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str) -> str:
        return value.strip()


class SkillUseResponse(BaseModel):
    skill: SkillSummary
    workflow: SkillWorkflow
