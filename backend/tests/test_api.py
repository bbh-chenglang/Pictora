from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_image_service
from app.main import app
from app.providers.base import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderRequestError,
    ProviderTimeoutError,
)
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult, ProviderModel
from app.schemas.generate import GenerateResponse


class FakeImageService:
    def __init__(self) -> None:
        self.generate_response = GenerateResponse(
            provider="openai",
            model="gpt-image-1",
            images=[ImageResult(url="https://example.com/image.png")],
        )
        self.analyze_response = AnalyzeResponse(
            provider="openai", model="vision-model", text="A red boat."
        )
        self.generate_calls = []
        self.analyze_calls = []

    async def list_providers(self):
        return [ProviderModel(id="openai", label="OpenAI", models=["gpt-image-1"])]

    async def generate(self, request):
        self.generate_calls.append(request)
        return self.generate_response

    async def analyze(self, provider, model, prompt, detail, image_bytes, content_type):
        self.analyze_calls.append(
            (provider, model, prompt, detail, image_bytes, content_type)
        )
        return self.analyze_response


@pytest.fixture
def service():
    fake = FakeImageService()
    app.dependency_overrides[get_image_service] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def test_list_providers_returns_safe_models(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.get("/api/providers")

    assert response.status_code == 200
    assert response.json() == {
        "providers": [{"id": "openai", "label": "OpenAI", "models": ["gpt-image-1"]}]
    }
    assert "keys" not in response.text
    assert "Settings" not in response.text


def test_generate_returns_service_response(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "provider": "openai",
                "model": "gpt-image-1",
                "prompt": "draw a boat",
                "detail": "high",
            },
        )

    assert response.status_code == 200
    assert response.json()["provider"] == "openai"
    assert service.generate_calls[0].prompt == "draw a boat"


def test_generate_rejects_empty_prompt(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={"provider": "openai", "model": "gpt-image-1", "prompt": ""},
        )

    assert response.status_code == 422


def test_analyze_accepts_jpeg(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            data={
                "provider": "openai",
                "model": "vision-model",
                "prompt": "What is here?",
                "detail": "auto",
            },
            files={"image": ("boat.jpg", b"jpeg bytes", "image/jpeg")},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "A red boat."
    assert service.analyze_calls[0][-1] == "image/jpeg"


@pytest.mark.parametrize(
    ("files", "expected_message"),
    [
        ({"image": ("empty.jpg", b"", "image/jpeg")}, "Image file is empty"),
        ({"image": ("file.txt", b"text", "text/plain")}, "Unsupported image type"),
    ],
)
def test_analyze_rejects_empty_or_unsupported_image(
    service: FakeImageService, files, expected_message: str
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            data={"provider": "openai", "model": "vision-model", "prompt": "Describe"},
            files=files,
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": {"code": "invalid_image", "message": expected_message}
    }


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ProviderNotFoundError("missing"), 400, "provider_not_found"),
        (ProviderTimeoutError(), 504, "provider_timeout"),
        (ProviderAuthError(), 401, "provider_auth"),
        (ProviderRequestError(), 502, "provider_request"),
    ],
)
def test_provider_errors_use_strict_error_response(
    error, status_code: int, code: str
) -> None:
    class ErrorService(FakeImageService):
        async def generate(self, request):
            raise error

    app.dependency_overrides[get_image_service] = ErrorService
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/generate",
                json={"provider": "openai", "model": "gpt-image-1", "prompt": "draw"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code, "message": error.message}}
    assert set(response.json()) == {"error"}
