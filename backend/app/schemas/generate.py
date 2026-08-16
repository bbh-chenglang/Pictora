from collections.abc import Sequence
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import GenerationViewSpec, ImageResult
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
    prompts: list[Annotated[str, Field(min_length=1, max_length=4000)]] | None = Field(
        default=None,
        max_length=8,
    )
    views: list[GenerationViewSpec] | None = Field(default=None, min_length=1, max_length=8)
    count: int = Field(default=1, ge=1, le=10)
    size: str | None = None
    aspect_ratio: Literal[
        "auto", "1:1", "1:2", "1:4", "1:8", "2:1", "2:3", "3:2", "3:4",
        "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "19.5:9",
        "9:19.5", "20:9", "9:20", "21:9",
    ] | None = None
    resolution: Literal["1K", "2K", "4K"] | None = None
    output_format: Literal["png", "jpeg", "webp"] | None = None
    background: Literal["auto", "opaque", "transparent"] | None = None
    output_compression: int | None = Field(default=None, ge=0, le=100)
    moderation: Literal["auto", "low"] | None = None

    @model_validator(mode="after")
    def validate_view_generation(self) -> "GenerateRequest":
        if self.views is not None and self.prompts is not None:
            raise ValueError("views and prompts cannot be used together")
        if self.views is not None and self.count != 1:
            raise ValueError("multi-view generation requires count=1")
        return self


class ImageGenerationFailure(BaseModel):
    position: int = Field(ge=0)
    error_code: str
    error_message: str


class GenerateResponse(BaseModel):
    provider: str
    model: str
    images: list[ImageResult]
    failures: list[ImageGenerationFailure] = Field(default_factory=list)


class GenerateTaskResponse(BaseModel):
    task_id: int
    history_id: int
    batch_id: int | None = None
    status: Literal["queued", "running", "pending"] = "queued"
    status_url: str


class CancelGenerationResponse(BaseModel):
    task_id: int
    history_id: int
    status: Literal["cancelled", "failed"] = "cancelled"
