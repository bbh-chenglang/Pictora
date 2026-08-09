from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    contact: str = Field(default="", max_length=200)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("留言不能为空")
        return normalized

    @field_validator("contact")
    @classmethod
    def normalize_contact(cls, value: str) -> str:
        return value.strip()


class FeedbackResponse(BaseModel):
    message: str
