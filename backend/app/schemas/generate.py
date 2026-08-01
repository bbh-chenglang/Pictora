from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ImageResult

ImageSize = Literal[
    "1024x1024",
    "1536x1024",
    "1024x1536",
]


class GenerateRequest(BaseModel):
    provider: str
    model: str
    prompt: str = Field(min_length=1, max_length=4000)
    detail: Literal["low", "high", "original", "auto"] = "auto"
    prompts: list[str] | None = Field(default=None, max_length=8)
    count: int = Field(default=1, ge=1, le=4)
    size: ImageSize = "1024x1024"


class GenerateResponse(BaseModel):
    provider: str
    model: str
    images: list[ImageResult]
