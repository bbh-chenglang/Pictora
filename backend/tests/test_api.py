import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.dependencies import (
    get_history_repository,
    get_history_service,
    get_image_service,
    get_settings_repository,
)
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
from app.repositories.settings_repository import SettingsRepository
from app.repositories.history_repository import HistoryRepository


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


class PassthroughHistoryService:
    async def generate(self, request, image_service):
        return await image_service.generate(request)

    async def analyze(
        self,
        *,
        image_service,
        provider,
        model,
        prompt,
        detail,
        image_bytes,
        content_type,
        filename,
    ):
        return await image_service.analyze(
            provider,
            model,
            prompt,
            detail,
            image_bytes,
            content_type,
        )


@pytest.fixture
def service():
    fake = FakeImageService()
    app.dependency_overrides[get_image_service] = lambda: fake
    app.dependency_overrides[get_history_service] = PassthroughHistoryService
    yield fake
    app.dependency_overrides.clear()


@pytest.fixture
def settings_repository(tmp_path: Path) -> SettingsRepository:
    database_path = tmp_path / "settings-api.db"
    asyncio.run(
        initialize_database(
            database_path,
            default_model="gpt-image-1.5",
            default_api_key="",
        )
    )
    return SettingsRepository(database_path)


@pytest.fixture
def empty_history_repository(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "empty-history.db"
    asyncio.run(initialize_database(database_path))
    return HistoryRepository(database_path)


@pytest.fixture
def history_repository_with_record(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "history-api.db"
    asyncio.run(initialize_database(database_path))
    repository = HistoryRepository(database_path)
    history_id = asyncio.run(
        repository.create(
            kind="generate",
            prompt="画一个苹果",
            provider="compatible",
            model="custom-model",
            detail="high",
            image_count=1,
        )
    )
    asyncio.run(
        repository.add_image(
            history_id=history_id,
            role="generated",
            mime_type="image/png",
            filename="result.png",
            position=0,
            data=b"png-bytes",
        )
    )
    asyncio.run(repository.complete(history_id, elapsed_ms=500))
    return repository


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


def test_generate_apple_image_prompt(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "provider": "openai",
                "model": "gpt-image-2",
                "prompt": "帮我生成一个苹果的图片",
                "detail": "auto",
                "count": 2,
            },
        )

    assert response.status_code == 200
    assert service.generate_calls[-1].provider == "openai"
    assert service.generate_calls[-1].model == "gpt-image-2"
    assert service.generate_calls[-1].prompt == "帮我生成一个苹果的图片"
    assert service.generate_calls[-1].count == 2


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
    app.dependency_overrides[get_history_service] = PassthroughHistoryService
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


def test_settings_api_updates_only_model_and_optional_key(
    settings_repository: SettingsRepository,
) -> None:
    app.dependency_overrides[get_settings_repository] = lambda: settings_repository
    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/settings",
                json={"model": "custom-image-model", "api_key": "private-key"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "provider_name": "北海AI",
        "model": "custom-image-model",
        "base_url": "https://sub.beibeihai.xyz/v1",
        "provider_id": "compatible",
        "api_key_configured": True,
    }
    assert "private-key" not in response.text


def test_settings_api_rejects_mutating_fixed_fields(
    settings_repository: SettingsRepository,
) -> None:
    app.dependency_overrides[get_settings_repository] = lambda: settings_repository
    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/settings",
                json={
                    "model": "custom-image-model",
                    "provider_name": "other",
                    "base_url": "https://other.example/v1",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_history_list_excludes_blob_data(
    history_repository_with_record: HistoryRepository,
) -> None:
    app.dependency_overrides[get_history_repository] = (
        lambda: history_repository_with_record
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/history")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["prompt"] == "画一个苹果"
    assert "data" not in response.text
    assert "base64" not in response.text


def test_history_detail_and_image_routes(
    history_repository_with_record: HistoryRepository,
) -> None:
    app.dependency_overrides[get_history_repository] = (
        lambda: history_repository_with_record
    )
    try:
        with TestClient(app) as client:
            detail = client.get("/api/history/1")
            image = client.get("/api/history/1/images/1")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert detail.json()["images"][0]["url"] == "/api/history/1/images/1"
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == b"png-bytes"


def test_missing_history_resources_return_404(
    empty_history_repository: HistoryRepository,
) -> None:
    app.dependency_overrides[get_history_repository] = (
        lambda: empty_history_repository
    )
    try:
        with TestClient(app) as client:
            detail = client.get("/api/history/999")
            image = client.get("/api/history/999/images/999")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "history_not_found"
    assert image.status_code == 404
    assert image.json()["error"]["code"] == "history_image_not_found"
