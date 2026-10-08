import pytest

from app.model_capabilities import (
    DEFAULT_MODEL_BY_PROVIDER,
    UnsupportedModelError,
    UnsupportedModelParameterError,
    filter_supported_model_ids,
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


@pytest.mark.parametrize(
    "model",
    ["gpt-image-2.5-sunburst", "gpt-image-2.5-flare"],
)
def test_gpt_image_25_models_support_their_extended_capabilities(model: str) -> None:
    capability = get_model_capabilities("gpt", model)
    request = normalize_generation_request(GenerateRequest(
        provider="openai",
        model=model,
        prompt="draw",
        size="1536x864",
        detail="max",
        background="transparent",
        output_format="png",
    ))

    assert [option.value for option in capability.qualities] == [
        "auto", "low", "medium", "high", "xhigh", "max",
    ]
    assert request.size == "1536x864"
    assert request.detail == "max"
    assert request.background == "transparent"


def test_gpt_image_model_filter_includes_registered_25_models() -> None:
    assert filter_supported_model_ids("gpt", [
        "gpt-image-2",
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
        "gpt-5",
    ]) == [
        "gpt-image-2",
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
    ]


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


def test_gemini_nano_banana_21_uses_latest_flash_image_capabilities() -> None:
    capability = get_model_capabilities("gemini", "gemini-nano-banana-2.1")
    request = normalize_generation_request(GenerateRequest(
        provider="gemini",
        model=capability.model,
        prompt="draw",
        aspect_ratio="1:8",
        resolution="4K",
    ))

    assert capability.label == "Gemini Nano Banana 2.1"
    assert capability.max_reference_images == 14
    assert capability.resolutions == ("1K", "2K", "4K")
    assert request.model == "gemini-nano-banana-2.1"
    assert request.aspect_ratio == "1:8"
    assert request.resolution == "4K"


def test_gemini_default_model_is_nano_banana_21() -> None:
    assert DEFAULT_MODEL_BY_PROVIDER["gemini"] == "gemini-nano-banana-2.1"


def test_gemini_three_pro_image_uses_native_pro_capabilities() -> None:
    capability = get_model_capabilities("gemini", "gemini-3-pro-image")
    request = normalize_generation_request(GenerateRequest(
        provider="gemini", model="gemini-3-pro-image", prompt="draw",
    ))

    assert capability.label == "Gemini 3 Pro Image"
    assert capability.max_reference_images == 14
    assert request.aspect_ratio == "1:1"
    assert request.resolution == "1K"


def test_output_and_reference_limits_are_declared() -> None:
    assert get_model_capabilities("gpt", "gpt-image-2").max_output_count == 4
    assert get_model_capabilities("grok", "grok-imagine-image").max_output_count == 4
    assert get_model_capabilities("gemini", "gemini-2.5-flash-image").max_reference_images == 3
    with pytest.raises(UnsupportedModelParameterError):
        normalize_generation_request(GenerateRequest(
            provider="gemini", model="gemini-2.5-flash-image", prompt="draw", count=5,
        ))


def test_gemini_flash_preview_keeps_its_upstream_model_id() -> None:
    capability = get_model_capabilities("gemini", "gemini-3.1-flash-image-preview")
    stable = get_model_capabilities("gemini", "gemini-3.1-flash-image")
    request = normalize_generation_request(GenerateRequest(
        provider="gemini", model=capability.model, prompt="draw",
        aspect_ratio="1:4", resolution="2K",
    ))

    assert capability.aspect_ratios == stable.aspect_ratios
    assert capability.resolutions == stable.resolutions
    assert capability.max_reference_images == stable.max_reference_images
    assert request.model == "gemini-3.1-flash-image-preview"
    assert request.aspect_ratio == "1:4"
    assert request.resolution == "2K"


def test_gemini_model_filter_includes_both_upstream_preview_models() -> None:
    assert filter_supported_model_ids("gemini", [
        "models/gemini-3.1-flash-image-preview",
        "models/gemini-3-pro-image-preview",
        "models/gemini-3.1-flash",
    ]) == [
        "gemini-3.1-flash-image-preview",
        "gemini-3-pro-image-preview",
    ]
