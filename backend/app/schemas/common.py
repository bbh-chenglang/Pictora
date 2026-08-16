from pydantic import BaseModel, Field


class ProviderModel(BaseModel):
    id: str
    label: str
    models: list[str]


class ImageResult(BaseModel):
    url: str | None = None
    base64_data: str | None = None
    mime_type: str | None = None
    revised_prompt: str | None = None
    generation_time_ms: int | None = None
    generation_position: int | None = None


class GenerationViewSpec(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=1, max_length=4000)


class ErrorBody(BaseModel):
    code: str
    message: str
