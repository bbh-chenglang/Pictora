import pytest
from pydantic import ValidationError

from app.schemas.generate import GenerateRequest


def test_generate_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(provider="openai", model="gpt-image-1", prompt="")


def test_generate_request_defaults_detail_to_auto() -> None:
    request = GenerateRequest(
        provider="openai",
        model="gpt-image-1",
        prompt="A lighthouse at sunset",
    )

    assert request.detail == "auto"


def test_generate_request_rejects_invalid_detail() -> None:
    with pytest.raises(ValidationError):
        GenerateRequest(
            provider="openai",
            model="gpt-image-1",
            prompt="A lighthouse at sunset",
            detail="medium",
        )
