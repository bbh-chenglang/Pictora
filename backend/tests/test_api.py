import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.dependencies import (
    get_current_user,
    get_history_repository,
    get_history_service,
    get_image_service,
    get_settings_repository,
)
from app.schemas.auth import StoredSessionUser
from app.auth import hash_password
from app.repositories.user_repository import UserRepository
from app.main import app
from app.providers.base import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderRequestError,
    ProviderTimeoutError,
)
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult, ProviderModel
from app.schemas.generate import GenerateResponse, ReferenceImage
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
        self.reference_images = []
        self.analyze_calls = []

    async def list_providers(self):
        return [ProviderModel(id="openai", label="OpenAI", models=["gpt-image-1"])]

    async def generate(self, request, reference_image=None):
        self.generate_calls.append(request)
        self.reference_images.append(reference_image)
        return self.generate_response

    async def analyze(
        self,
        provider,
        model,
        prompt,
        detail,
        image_bytes,
        content_type,
        reference_images=None,
    ):
        call = (provider, model, prompt, detail, image_bytes, content_type)
        self.analyze_calls.append(call + ((reference_images,) if reference_images else ()))
        return self.analyze_response


def wait_for_generation(service: FakeImageService) -> None:
    deadline = time.monotonic() + 1
    while not service.generate_calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert service.generate_calls


def test_version_is_public_and_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "release-2026.08.12")
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"version": "release-2026.08.12"}
    assert response.headers["cache-control"] == "no-store"


class PassthroughHistoryService:
    async def create_generation(self, request, user_id, reference_image=None):
        self.request = request
        self.reference_image = reference_image
        return 101

    async def execute_generation(
        self, history_id, request, image_service, user_id, reference_image=None
    ):
        if reference_image is not None:
            return await image_service.generate(request, reference_image)
        return await image_service.generate(request)

    async def cancel_generation(self, history_id):
        return None

    async def analyze(
        self,
        *,
        user_id,
        image_service,
        provider,
        model,
        prompt,
        detail,
        image_bytes,
        content_type,
        filename,
        reference_images=None,
    ):
        analyze_kwargs = {}
        if reference_images is not None:
            analyze_kwargs["reference_images"] = reference_images
        return await image_service.analyze(
            provider,
            model,
            prompt,
            detail,
            image_bytes,
            content_type,
            **analyze_kwargs,
        )


@pytest.fixture(autouse=True)
def authenticated_user():
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(id=1, username="alice", api_key="", model="gpt-image-1.5")
    yield
    app.dependency_overrides.clear()


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
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    return SettingsRepository(database_path)


@pytest.fixture
def empty_history_repository(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "empty-history.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    return HistoryRepository(database_path)


@pytest.fixture
def history_repository_with_record(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "history-api.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    repository = HistoryRepository(database_path)
    history_id = asyncio.run(
        repository.create(
            user_id=1,
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
            user_id=1,
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
        wait_for_generation(service)

    assert response.status_code == 202
    assert response.json() == {
        "task_id": 101,
        "status": "pending",
        "status_url": "/api/history/101",
    }
    assert service.generate_calls[0].prompt == "draw a boat"


def test_generate_accepts_an_existing_conversation(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "conversation_id": 42,
                "provider": "openai",
                "model": "gpt-image-1",
                "prompt": "continue this conversation",
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].conversation_id == 42


def test_generate_with_reference_uploads_image_and_parameters(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate/reference",
            data={
                "conversation_id": "42",
                "provider": "gemini",
                "model": "gemini-3.1-flash-image",
                "prompt": "保留参考图构图并调整光线",
                "count": "1",
                "size": "16:9",
                "aspect_ratio": "16:9",
                "resolution": "4K",
            },
            files={"image": ("room.jpg", b"reference-bytes", "image/jpeg")},
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].prompt == "保留参考图构图并调整光线"
    assert service.generate_calls[-1].conversation_id == 42
    assert service.generate_calls[-1].aspect_ratio == "16:9"
    assert service.generate_calls[-1].resolution == "4K"
    reference = service.reference_images[-1]
    assert reference is not None
    assert reference.data == b"reference-bytes"
    assert reference.content_type == "image/jpeg"
    assert reference.filename == "room.jpg"


def test_generate_with_multiple_reference_images(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate/reference",
            data={
                "provider": "gemini",
                "model": "gemini-3.1-flash-image",
                "prompt": "融合空间与材质参考",
                "image_categories": ["environment", "object"],
            },
            files=[
                ("images", ("room.jpg", b"room-bytes", "image/jpeg")),
                ("images", ("material.png", b"material-bytes", "image/png")),
            ],
        )
        wait_for_generation(service)

    assert response.status_code == 202
    references = service.reference_images[-1]
    assert isinstance(references, list)
    assert [reference.filename for reference in references] == ["room.jpg", "material.png"]
    assert [reference.data for reference in references] == [b"room-bytes", b"material-bytes"]
    assert [reference.category for reference in references] == ["environment", "object"]


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
                "size": "2:3",
                "aspect_ratio": "2:3",
                "resolution": "2K",
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].provider == "openai"
    assert service.generate_calls[-1].model == "gpt-image-2"
    assert service.generate_calls[-1].prompt == "帮我生成一个苹果的图片"
    assert service.generate_calls[-1].count == 2
    assert service.generate_calls[-1].size == "2:3"
    assert service.generate_calls[-1].aspect_ratio == "2:3"
    assert service.generate_calls[-1].resolution == "2K"


def test_generate_rejects_empty_prompt(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={"provider": "openai", "model": "gpt-image-1", "prompt": ""},
        )

    assert response.status_code == 422


def test_generate_accepts_custom_size(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "provider": "openai",
                "model": "gpt-image-2",
                "prompt": "draw",
                "size": "1000x1000",
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].size == "1000x1000"


def test_generate_accepts_nonstandard_landscape_size(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "provider": "openai",
                "model": "gpt-image-1.5",
                "prompt": "draw",
                "size": "1536x864",
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].size == "1536x864"


def test_generate_accepts_square_size(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "provider": "openai",
                "model": "gpt-image-2",
                "prompt": "draw a square icon",
                "size": "1024x1024",
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].size == "1024x1024"


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


def test_analyze_accepts_multiple_images(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            data={
                "provider": "openai",
                "model": "vision-model",
                "prompt": "比较这些图片",
            },
            files=[
                ("images", ("first.jpg", b"first", "image/jpeg")),
                ("images", ("second.png", b"second", "image/png")),
            ],
        )

    assert response.status_code == 200
    references = service.analyze_calls[-1][-1]
    assert [reference.filename for reference in references] == ["first.jpg", "second.png"]


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
        async def analyze(self, *args, **kwargs):
            raise error

    app.dependency_overrides[get_image_service] = ErrorService
    app.dependency_overrides[get_history_service] = PassthroughHistoryService
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/analyze",
                data={"provider": "openai", "model": "vision-model", "prompt": "describe"},
                files={"image": ("input.png", b"png", "image/png")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status_code
    assert response.json() == {"error": {"code": code, "message": error.message}}
    assert set(response.json()) == {"error"}


def test_provider_request_error_forwards_upstream_response() -> None:
    upstream_body = b'{"error":{"message":"rate limited","type":"upstream_error"}}'
    error = ProviderRequestError(
        status_code=429,
        response_content=upstream_body,
        content_type="application/json",
    )

    class ErrorService(FakeImageService):
        async def analyze(self, *args, **kwargs):
            raise error

    app.dependency_overrides[get_image_service] = ErrorService
    app.dependency_overrides[get_history_service] = PassthroughHistoryService
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/analyze",
                data={"provider": "openai", "model": "vision-model", "prompt": "describe"},
                files={"image": ("input.png", b"png", "image/png")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 429
    assert response.content == upstream_body
    assert response.headers["content-type"] == "application/json"


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
    assert image.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert image.content == b"png-bytes"


def test_history_image_edit_snapshot_and_delete_routes(
    history_repository_with_record: HistoryRepository,
) -> None:
    app.dependency_overrides[get_history_repository] = (
        lambda: history_repository_with_record
    )
    try:
        with TestClient(app) as client:
            snapshot = client.get("/api/history/1/images/1/edit")
            deleted = client.delete("/api/history/1/images/1")
            missing = client.get("/api/history/1/images/1")
    finally:
        app.dependency_overrides.clear()

    assert snapshot.status_code == 200
    assert snapshot.json() == {
        "history_id": 1,
        "image_id": 1,
        "api_key_config_id": None,
        "prompt": "画一个苹果",
        "provider": "compatible",
        "model": "custom-model",
        "detail": "high",
        "image_count": 1,
        "size": None,
        "resolution": None,
        "references": [],
    }
    assert deleted.status_code == 204
    assert missing.status_code == 404


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
