from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ImageResult


class GenerateRequest(BaseModel):
    provider: str
    model: str
    prompt: str = Field(min_length=1, max_length=4000)
    detail: Literal["low", "high", "original", "auto"] = "auto"


class GenerateResponse(BaseModel):
    provider: str
    model: str
    images: list[ImageResult]
