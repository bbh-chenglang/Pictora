from pydantic import BaseModel


class AnalyzeResponse(BaseModel):
    provider: str
    model: str
    text: str
