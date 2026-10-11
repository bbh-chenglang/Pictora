import json

from pydantic import AliasChoices, BaseModel, Field, field_validator


class TaskDiagnostics(BaseModel):
    error_details: dict | None = Field(default=None, validation_alias=AliasChoices("error_details", "error_details_json"))

    @field_validator("error_details", mode="before")
    @classmethod
    def decode_details(cls, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return None
        return value if isinstance(value, dict) else None
