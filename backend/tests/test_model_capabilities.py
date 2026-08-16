import pytest

from app.model_capabilities import (
    UnsupportedModelError,
    UnsupportedModelParameterError,
    get_model_capabilities,
    normalize_generation_request,
)
from app.schemas.generate import GenerateRequest


def test_unknown_models_are_rejected() -> None:
    with pytest.raises(UnsupportedModelError):
        get_model_capabilities("gpt", "gpt-5")


def test_provider_model_mismatch_is_rejected() -> None:
    with pytest.raises(UnsupportedModelError):
        get_model_capabilities("gemini", "gpt-image-2")


def test_gpt_image_two_accepts_registered_advanced_size() -> None:
    request = normalize_generation_request(GenerateRequest(
        provider="openai", model="gpt-image-2", prompt="draw", size="2048x1152", detail="high",
    ))
    assert request.provider == "openai"
    assert request.size == "2048x1152"
    assert request.detail == "high"


def test_gemini_defaults_and_rejects_unsupported_quality() -> None:
    request = normalize_generation_request(GenerateRequest(
        provider="gemini", model="gemini-3.1-flash-image", prompt="draw",
    ))
    assert request.aspect_ratio == "1:1"
    assert request.resolution == "1K"
    with pytest.raises(UnsupportedModelParameterError):
        normalize_generation_request(GenerateRequest(
            provider="gemini", model="gemini-3.1-flash-image", prompt="draw", detail="high",
        ))


def test_output_and_reference_limits_are_declared() -> None:
    assert get_model_capabilities("gpt", "gpt-image-2").max_output_count == 4
    assert get_model_capabilities("grok", "grok-imagine-image").max_output_count == 4
    assert get_model_capabilities("gemini", "gemini-2.5-flash-image").max_reference_images == 3
    with pytest.raises(UnsupportedModelParameterError):
        normalize_generation_request(GenerateRequest(
            provider="gemini", model="gemini-2.5-flash-image", prompt="draw", count=5,
        ))
