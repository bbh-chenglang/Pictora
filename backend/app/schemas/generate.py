from collections.abc import Sequence
import re
from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator

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
    def normalize_provider_parameters(self) -> "GenerateRequest":
        if self.provider == "grok":
            self.size = None
            self.output_format = None
            self.background = None
            self.output_compression = None
            self.moderation = None
            grok_ratios = {
                "auto", "1:1", "1:2", "2:1", "2:3", "3:2", "3:4", "4:3",
                "9:16", "16:9", "19.5:9", "9:19.5", "20:9", "9:20",
            }
            if self.aspect_ratio is not None and self.aspect_ratio not in grok_ratios:
                raise ValueError("The selected Grok model does not support this aspect ratio")
            if self.resolution == "4K":
                raise ValueError("Grok supports only 1K or 2K resolution")
            if self.model.casefold() == "grok-imagine-image-2.0":
                if self.detail not in {"auto", "low", "medium"}:
                    raise ValueError("Grok Imagine Image 2.0 supports low or medium quality")
                if self.detail == "auto":
                    self.detail = "medium"
            else:
                self.detail = "auto"
        elif self.provider == "gemini":
            if self.count > 4:
                raise ValueError("Gemini supports at most 4 images per request")
            self.detail = "auto"
            self.output_format = None
            self.background = None
            self.output_compression = None
            self.moderation = None
            model = self.model.casefold()
            gemini_ratios = {
                "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9",
            }
            if "gemini-3.1-flash-image" in model:
                gemini_ratios.update({"1:4", "1:8", "4:1", "8:1"})
            if self.aspect_ratio is not None and self.aspect_ratio not in gemini_ratios:
                raise ValueError("The selected Gemini model does not support this aspect ratio")
            if "gemini-3" not in model or "lite-image" in model:
                self.resolution = None
        else:
            self.aspect_ratio = None
            self.resolution = None
            self.size = self.size or "auto"
            model = self.model.casefold()
            is_gpt_image_2 = model.startswith("gpt-image-2")
            legacy_sizes = {"auto", "1024x1024", "1536x1024", "1024x1536"}
            if not is_gpt_image_2 and self.size not in legacy_sizes:
                raise ValueError("The selected GPT image model does not support this size")
            if is_gpt_image_2 and self.size != "auto":
                match = re.fullmatch(r"(\d+)x(\d+)", self.size)
                if match is None:
                    raise ValueError("GPT image size must be auto or WIDTHxHEIGHT")
                width, height = map(int, match.groups())
                short_edge, long_edge = sorted((width, height))
                pixels = width * height
                if (
                    width % 16 or height % 16 or long_edge > 3840
                    or long_edge > short_edge * 3
                    or pixels < 655_360 or pixels > 8_294_400
                ):
                    raise ValueError("GPT image size is outside the supported range")
            if self.output_format == "png":
                self.output_compression = None
            if self.background == "transparent" and self.output_format == "jpeg":
                raise ValueError("Transparent backgrounds require PNG or WebP output")
            if is_gpt_image_2 and self.background == "transparent":
                raise ValueError("GPT Image 2 does not support transparent backgrounds")
        return self


class GenerateResponse(BaseModel):
    provider: str
    model: str
    images: list[ImageResult]


class GenerateTaskResponse(BaseModel):
    task_id: int
    batch_id: int | None = None
    status: Literal["pending"] = "pending"
    status_url: str


class CancelGenerationResponse(BaseModel):
    task_id: int
    status: Literal["failed"] = "failed"
