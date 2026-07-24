import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
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


def test_settings_use_secret_str_for_empty_api_key_defaults() -> None:
    settings = Settings(_env_file=None)

    assert isinstance(settings.openai_api_key, SecretStr)
    assert isinstance(settings.custom_api_key, SecretStr)
    assert settings.openai_api_key.get_secret_value() == ""
    assert settings.custom_api_key.get_secret_value() == ""


def test_settings_load_api_keys_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-test-key")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key.get_secret_value() == "openai-test-key"
    assert settings.custom_api_key.get_secret_value() == "custom-test-key"
