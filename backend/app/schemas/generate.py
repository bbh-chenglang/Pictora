from collections.abc import Sequence
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field

from app.schemas.common import ImageResult
from app.schemas.history import ReferenceCategory


class ReferenceImage(BaseModel):
    data: bytes
    content_type: str
    filename: str | None = None
    category: ReferenceCategory = "person"


ReferenceImageInput: TypeAlias = ReferenceImage | Sequence[ReferenceImage]


def normalize_reference_images(
    reference_image: ReferenceImageInput | None,
) -> list[ReferenceImage]:
    if reference_image is None:
        return []
    if isinstance(reference_image, ReferenceImage):
        return [reference_image]
    return list(reference_image)


class GenerateRequest(BaseModel):
    project_id: int | None = None
    conversation_id: int | None = Field(default=None, gt=0)
    api_key_config_id: int | None = Field(default=None, gt=0)
    provider: str
    model: str
    prompt: str = Field(min_length=1, max_length=4000)
    detail: Literal["low", "medium", "high", "original", "auto"] = "auto"
    prompts: list[str] | None = Field(default=None, max_length=8)
    count: int = Field(default=1, ge=1, le=4)
    size: str = "1024x1024"
    aspect_ratio: Literal["1:1", "3:2", "2:3", "9:16", "16:9"] | None = None
    resolution: Literal["1K", "2K", "4K"] | None = None


class GenerateResponse(BaseModel):
    provider: str
    model: str
    images: list[ImageResult]


class GenerateTaskResponse(BaseModel):
    task_id: int
    status: Literal["pending"] = "pending"
    status_url: str


class CancelGenerationResponse(BaseModel):
    task_id: int
    status: Literal["failed"] = "failed"
