from pydantic import BaseModel


class ProviderModel(BaseModel):
    id: str
    label: str
    models: list[str]


class ImageResult(BaseModel):
    url: str | None = None
    base64_data: str | None = None
    revised_prompt: str | None = None
    generation_time_ms: int | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
