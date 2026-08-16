import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.api import upload_limits
from app.api import history as history_api

from app.database import initialize_database
from app.image_thumbnails import WebPThumbnail
from app.dependencies import (
    get_current_user,
    get_generation_task_manager,
    get_history_repository,
    get_history_service,
    get_image_service,
    get_project_repository,
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
from app.model_capabilities import normalize_generation_request, get_model_capabilities
from app.schemas.generate import normalize_reference_images
from app.repositories.settings_repository import SettingsRepository
from app.repositories.history_repository import HistoryRepository
from app.repositories.project_repository import ProjectRepository
from app.services.generation_task_manager import GenerationTaskManager
from app.services.history_service import HistoryService


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

    async def normalize_request(self, request, reference_image=None):
        normalized = normalize_generation_request(request)
        if len(normalize_reference_images(reference_image)) > get_model_capabilities(normalized.provider, normalized.model).max_reference_images:
            raise ValueError("too many reference images")
        return normalized

    async def generate(self, request, reference_image=None):
        self.generate_calls.append(normalize_generation_request(request))
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


class RecordingTaskManager:
    worker_id = "api-test-worker"

    def __init__(self) -> None:
        self.cancelled: list[int] = []

    async def cancel(self, task_id: int) -> bool:
        self.cancelled.append(task_id)
        return True


def wait_for_generation(service: FakeImageService) -> None:
    deadline = time.monotonic() + 1
    while not service.generate_calls and time.monotonic() < deadline:
        time.sleep(0.01)
    assert service.generate_calls


@pytest.mark.parametrize("configured_version", ["V1", "V2", None])
def test_version_is_public_and_not_cached(
    monkeypatch: pytest.MonkeyPatch, configured_version: str | None
) -> None:
    if configured_version is None:
        monkeypatch.delenv("APP_VERSION", raising=False)
    else:
        monkeypatch.setenv("APP_VERSION", configured_version)
    app.dependency_overrides.pop(get_current_user, None)

    with TestClient(app) as client:
        response = client.get("/api/version")

    assert response.status_code == 200
    assert response.json() == {"version": configured_version or "dev"}
    assert response.headers["cache-control"] == "no-store"


class PassthroughHistoryService:
    async def create_generation(
        self, request, user_id, reference_image=None, *, include_batch_id=False
    ):
        self.request = request
        self.reference_image = reference_image
        return (101, 201) if include_batch_id else 101

    async def execute_generation(
        self,
        history_id,
        request,
        image_service,
        user_id,
        reference_image=None,
        *,
        batch_id=None,
        task_id=None,
        worker_id=None,
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
    payload = response.json()
    assert payload["providers"] == [{"id": "openai", "label": "OpenAI", "models": ["gpt-image-1"]}]
    assert payload["capabilities"]
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
        "history_id": 101,
        "batch_id": 201,
        "status": "queued",
        "status_url": "/api/generation-tasks/101",
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


def test_generate_accepts_a_second_batch_while_the_first_is_pending(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "concurrent-conversation-api.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    repository = HistoryRepository(database_path)
    project_repository = ProjectRepository(database_path)
    history_service = HistoryService(repository, project_repository=project_repository)
    image_service = FakeImageService()
    image_service.generate_response = GenerateResponse(
        provider="compatible",
        model="gpt-image-1.5",
        images=[ImageResult(base64_data="data:image/png;base64,cG5n")],
    )
    manager = GenerationTaskManager(max_active_tasks=4, max_tasks_per_user=4)

    async def create_pending_history() -> int:
        project_id = (await project_repository.list_with_history(1))[0].id
        return await repository.create(
            user_id=1,
            project_id=project_id,
            kind="generate",
            prompt="第一批仍在生成",
            provider="compatible",
            model="gpt-image-1.5",
            detail="auto",
            image_count=1,
        )

    history_id = asyncio.run(create_pending_history())
    app.dependency_overrides[get_history_repository] = lambda: repository
    app.dependency_overrides[get_project_repository] = lambda: project_repository
    app.dependency_overrides[get_history_service] = lambda: history_service
    app.dependency_overrides[get_image_service] = lambda: image_service
    app.dependency_overrides[get_generation_task_manager] = lambda: manager
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/generate",
                json={
                    "conversation_id": history_id,
                    "provider": "compatible",
                    "model": "gpt-image-1.5",
                    "prompt": "第二批同时生成",
                },
            )
    finally:
        app.dependency_overrides.clear()

    detail = asyncio.run(repository.get(1, history_id))
    assert response.status_code == 202
    assert detail is not None
    assert detail.prompt == "第二批同时生成"
    assert len(detail.batches) == 2


def test_generate_rejects_before_persistence_when_queue_is_full(
    service: FakeImageService,
) -> None:
    class RecordingHistoryService(PassthroughHistoryService):
        called = False

        async def create_generation(self, *args, **kwargs):
            self.called = True
            return await super().create_generation(*args, **kwargs)

    history_service = RecordingHistoryService()
    manager = GenerationTaskManager(max_active_tasks=1, max_tasks_per_user=1)
    assert manager.try_reserve(1)
    app.dependency_overrides[get_history_service] = lambda: history_service
    app.dependency_overrides[get_generation_task_manager] = lambda: manager
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/generate",
                json={
                    "provider": "openai",
                    "model": "gpt-image-1",
                    "prompt": "should not be persisted",
                },
            )
    finally:
        app.dependency_overrides.pop(get_history_service, None)
        app.dependency_overrides.pop(get_generation_task_manager, None)
        manager.release_reservation(1)

    assert response.status_code == 429
    assert response.json() == {
        "error": {
            "code": "generation_queue_full",
            "message": "生成队列已满，请等待当前任务完成后重试",
        }
    }
    assert not history_service.called


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


def test_generate_with_multi_view_form_data(service: FakeImageService) -> None:
    views = [
        {"key": "person_front", "label": "正面", "prompt": "正面提示词"},
        {"key": "person_back", "label": "背面", "prompt": "背面提示词"},
    ]
    with TestClient(app) as client:
        response = client.post(
            "/api/generate/reference",
            data={
                "provider": "gemini",
                "model": "gemini-3.1-flash-image",
                "prompt": "基础提示词",
                "count": "1",
                "views": json.dumps(views, ensure_ascii=False),
                "image_categories": "person",
            },
            files={"images": ("person.png", b"person", "image/png")},
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert [view.model_dump() for view in service.generate_calls[-1].views or []] == views


def test_generate_rejects_invalid_multi_view_form_data(service: FakeImageService) -> None:
    with TestClient(app) as client:
        malformed = client.post(
            "/api/generate/reference",
            data={
                "provider": "gemini",
                "model": "gemini-3.1-flash-image",
                "prompt": "基础提示词",
                "views": "not-json",
            },
            files={"images": ("person.png", b"person", "image/png")},
        )
        mixed = client.post(
            "/api/generate/reference",
            data={
                "provider": "gemini",
                "model": "gemini-3.1-flash-image",
                "prompt": "基础提示词",
                "views": json.dumps([{"key": "person_front", "label": "正面", "prompt": "正面"}]),
                "prompts": "批量提示词",
            },
            files={"images": ("person.png", b"person", "image/png")},
        )

    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "invalid_generation_views"
    assert mixed.status_code == 422


def test_grok_reference_generation_accepts_four_images_and_limits_references(
    service: FakeImageService,
) -> None:
    files = [
        ("images", (f"reference-{index}.png", f"bytes-{index}".encode(), "image/png"))
        for index in range(3)
    ]
    with TestClient(app) as client:
        response = client.post(
            "/api/generate/reference",
            data={
                "provider": "grok",
                "model": "grok-imagine-image",
                "prompt": "生成四张方案",
                "count": "4",
                "size": "16:9",
                "aspect_ratio": "16:9",
                "resolution": "2K",
                "detail": "auto",
            },
            files=files,
        )
        wait_for_generation(service)

        too_many = client.post(
            "/api/generate/reference",
            data={
                "provider": "grok",
                "model": "grok-imagine-image",
                "prompt": "参考图过多",
            },
            files=files + [("images", ("fourth.png", b"fourth", "image/png"))],
        )

    request = service.generate_calls[-1]
    assert response.status_code == 202
    assert request.count == 4
    assert request.detail == "auto"
    assert request.size is None
    assert request.aspect_ratio == "16:9"
    assert request.resolution == "2K"
    assert too_many.status_code == 422


def test_gpt_generation_accepts_four_images(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "provider": "openai",
                "model": "gpt-image-2",
                "prompt": "too many",
                "count": 4,
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].count == 4


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("openai", "gpt-image-2"),
        ("grok", "grok-imagine-image"),
        ("gemini", "gemini-3.1-flash-image"),
    ],
)
def test_generation_rejects_more_than_four_images(
    service: FakeImageService,
    provider: str,
    model: str,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/generate",
            json={
                "provider": provider,
                "model": model,
                "prompt": "too many",
                "count": 5,
            },
        )

    assert response.status_code == 422


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
                "size": "1152x2048",
                "output_format": "webp",
                "background": "opaque",
                "output_compression": 85,
                "moderation": "low",
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].provider == "openai"
    assert service.generate_calls[-1].model == "gpt-image-2"
    assert service.generate_calls[-1].prompt == "帮我生成一个苹果的图片"
    assert service.generate_calls[-1].count == 2
    assert service.generate_calls[-1].size == "1152x2048"
    assert service.generate_calls[-1].aspect_ratio is None
    assert service.generate_calls[-1].resolution is None
    assert service.generate_calls[-1].output_format == "webp"
    assert service.generate_calls[-1].background == "opaque"
    assert service.generate_calls[-1].output_compression == 85
    assert service.generate_calls[-1].moderation == "low"


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
                "size": "1280x1280",
            },
        )
        wait_for_generation(service)

    assert response.status_code == 202
    assert service.generate_calls[-1].size == "1280x1280"


def test_legacy_gpt_model_rejects_nonstandard_landscape_size(service: FakeImageService) -> None:
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

    assert response.status_code == 422


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


def test_reference_uploads_enforce_file_and_total_size_limits(
    service: FakeImageService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(upload_limits, "MAX_REFERENCE_FILE_BYTES", 4)
    monkeypatch.setattr(upload_limits, "MAX_REFERENCE_TOTAL_BYTES", 6)
    with TestClient(app) as client:
        per_file = client.post(
            "/api/generate/reference",
            data={"provider": "openai", "model": "gpt-image-1", "prompt": "draw"},
            files={"image": ("large.png", b"12345", "image/png")},
        )
        total = client.post(
            "/api/analyze",
            data={"provider": "openai", "model": "vision-model", "prompt": "compare"},
            files=[
                ("images", ("first.png", b"1234", "image/png")),
                ("images", ("second.png", b"5678", "image/png")),
            ],
        )

    assert per_file.status_code == 413
    assert per_file.json()["error"]["code"] == "image_too_large"
    assert total.status_code == 413
    assert total.json()["error"]["code"] == "image_too_large"


def test_analyze_rejects_prompts_over_4000_characters(service: FakeImageService) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/analyze",
            data={"provider": "openai", "model": "vision-model", "prompt": "x" * 4001},
            files={"image": ("input.png", b"png", "image/png")},
        )
    assert response.status_code == 422


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


def test_provider_request_error_returns_only_sanitized_json() -> None:
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

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_request",
            "message": "Provider request failed (HTTP 429): rate limited",
        }
    }
    assert response.content != upstream_body
    assert response.headers["content-type"].startswith("application/json")


def test_settings_api_updates_only_model_and_optional_key(
    settings_repository: SettingsRepository,
) -> None:
    app.dependency_overrides[get_settings_repository] = lambda: settings_repository
    try:
        with TestClient(app) as client:
            response = client.put(
                "/api/settings",
                json={"model": "gpt-image-1", "api_key": "private-key"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "provider_name": "北海AI",
        "model": "gpt-image-1",
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
                    "model": "gpt-image-1",
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


def test_cancel_generation_targets_only_the_requested_task(tmp_path: Path) -> None:
    database_path = tmp_path / "cancel-generation-api.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    repository = HistoryRepository(database_path)

    async def create_tasks() -> tuple[int, int, int, int]:
        first_history_id = await repository.create(
            user_id=1,
            project_id=1,
            kind="generate",
            prompt="第一批",
            provider="compatible",
            model="custom-model",
            detail="auto",
            image_count=1,
        )
        first_batch_id = await repository.latest_generation_batch_id(
            user_id=1,
            history_id=first_history_id,
        )
        first_task_id = await repository.create_generation_task(
            user_id=1,
            history_id=first_history_id,
            batch_id=first_batch_id,
        )
        second_history_id = await repository.create(
            user_id=1,
            project_id=1,
            kind="generate",
            prompt="第二批",
            provider="compatible",
            model="custom-model",
            detail="auto",
            image_count=1,
        )
        second_batch_id = await repository.latest_generation_batch_id(
            user_id=1,
            history_id=second_history_id,
        )
        second_task_id = await repository.create_generation_task(
            user_id=1,
            history_id=second_history_id,
            batch_id=second_batch_id,
        )
        return first_history_id, second_history_id, first_task_id, second_task_id

    first_history_id, second_history_id, first_task_id, second_task_id = asyncio.run(create_tasks())
    manager = RecordingTaskManager()
    app.dependency_overrides[get_history_repository] = lambda: repository
    app.dependency_overrides[get_generation_task_manager] = lambda: manager
    try:
        with TestClient(app) as client:
            response = client.delete(f"/api/generate/{first_task_id}")
    finally:
        app.dependency_overrides.clear()

    first = asyncio.run(repository.get_generation_task(1, first_task_id))
    second = asyncio.run(repository.get_generation_task(1, second_task_id))
    first_detail = asyncio.run(repository.get(1, first_history_id))
    second_detail = asyncio.run(repository.get(1, second_history_id))

    assert response.status_code == 200
    assert response.json() == {
        "task_id": first_task_id,
        "history_id": first_history_id,
        "status": "cancelled",
    }
    assert manager.cancelled == [first_task_id]
    assert first is not None and first["status"] == "cancelled"
    assert second is not None and second["status"] == "queued"
    assert first_detail is not None and first_detail.status == "failed"
    assert second_detail is not None and second_detail.status == "pending"


def test_generation_task_api_returns_immutable_batch_snapshot(tmp_path: Path) -> None:
    database_path = tmp_path / "generation-task-snapshot-api.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    repository = HistoryRepository(database_path)

    async def create_task() -> tuple[int, int]:
        history_id = await repository.create(
            user_id=1,
            project_id=1,
            kind="generate",
            prompt="批次自己的提示词",
            provider="gemini",
            model="gemini-3.1-flash-image",
            detail="auto",
            image_count=3,
            size="16:9",
            resolution="2K",
        )
        batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
        task_id = await repository.create_generation_task(
            user_id=1,
            history_id=history_id,
            batch_id=batch_id,
        )
        return history_id, task_id

    history_id, task_id = asyncio.run(create_task())
    app.dependency_overrides[get_history_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            listed = client.get("/api/generation-tasks")
            detail = client.get(f"/api/generation-tasks/{task_id}")
    finally:
        app.dependency_overrides.clear()

    assert listed.status_code == detail.status_code == 200
    snapshot = detail.json()
    assert snapshot == listed.json()[0]
    assert snapshot["history_id"] == history_id
    assert snapshot["project_id"] == 1
    assert snapshot["prompt"] == "批次自己的提示词"
    assert snapshot["provider"] == "gemini"
    assert snapshot["image_count"] == 3
    assert snapshot["size"] == "16:9"
    assert snapshot["resolution"] == "2K"


@pytest.mark.parametrize("delete_scope", ["project", "history"])
def test_deleting_active_generation_cancels_worker_before_cascade(
    tmp_path: Path,
    delete_scope: str,
) -> None:
    database_path = tmp_path / f"delete-active-{delete_scope}.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    history_repository = HistoryRepository(database_path)
    project_repository = ProjectRepository(database_path)

    async def create_task() -> tuple[int, int, int]:
        project_id = (await project_repository.list_with_history(1))[0].id
        history_id = await history_repository.create(
            user_id=1,
            project_id=project_id,
            kind="generate",
            prompt="删除中的任务",
            provider="compatible",
            model="custom-model",
            detail="auto",
            image_count=2,
        )
        batch_id = await history_repository.latest_generation_batch_id(user_id=1, history_id=history_id)
        task_id = await history_repository.create_generation_task(
            user_id=1,
            history_id=history_id,
            batch_id=batch_id,
        )
        return project_id, history_id, task_id

    project_id, history_id, task_id = asyncio.run(create_task())
    manager = RecordingTaskManager()
    app.dependency_overrides[get_project_repository] = lambda: project_repository
    app.dependency_overrides[get_history_repository] = lambda: history_repository
    app.dependency_overrides[get_generation_task_manager] = lambda: manager
    try:
        with TestClient(app) as client:
            response = (
                client.delete(f"/api/projects/{project_id}")
                if delete_scope == "project"
                else client.request(
                    "DELETE",
                    f"/api/projects/{project_id}/history",
                    json={"history_ids": [history_id]},
                )
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert manager.cancelled == [task_id]
    assert asyncio.run(history_repository.get_generation_task(1, task_id)) is None
    assert asyncio.run(history_repository.get(1, history_id)) is None


def test_history_detail_and_image_routes(
    history_repository_with_record: HistoryRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thumbnail_generation_calls: list[bytes] = []

    def create_thumbnail(image_data: bytes) -> WebPThumbnail:
        thumbnail_generation_calls.append(image_data)
        return WebPThumbnail(data=b"webp-thumbnail", width=512, height=256)

    monkeypatch.setattr(history_api, "create_webp_thumbnail", create_thumbnail)
    app.dependency_overrides[get_history_repository] = (
        lambda: history_repository_with_record
    )
    try:
        with TestClient(app) as client:
            detail = client.get("/api/history/1")
            image = client.get("/api/history/1/images/1")
            cached_image = client.get(
                "/api/history/1/images/1",
                headers={"If-None-Match": image.headers["etag"]},
            )
            thumbnail = client.get("/api/history/1/images/1/thumbnail?v=1")
            stored_thumbnail = client.get("/api/history/1/images/1/thumbnail?v=1")
            cached_thumbnail = client.get(
                "/api/history/1/images/1/thumbnail?v=1",
                headers={"If-None-Match": thumbnail.headers["etag"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 200
    assert detail.json()["images"][0]["url"] == "/api/history/1/images/1"
    assert detail.json()["images"][0]["thumbnail_url"] == (
        "/api/history/1/images/1/thumbnail?v=1"
    )
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert image.headers["etag"] == '"history-1-image-1"'
    assert image.headers["vary"] == "Cookie"
    assert image.content == b"png-bytes"
    assert cached_image.status_code == 304
    assert cached_image.headers["cache-control"] == image.headers["cache-control"]
    assert cached_image.headers["etag"] == image.headers["etag"]
    assert cached_image.headers["vary"] == "Cookie"
    assert cached_image.content == b""
    assert thumbnail.status_code == 200
    assert thumbnail.headers["content-type"] == "image/webp"
    assert thumbnail.headers["cache-control"] == image.headers["cache-control"]
    assert thumbnail.headers["etag"] == '"history-1-image-1-thumbnail-v1"'
    assert thumbnail.content == b"webp-thumbnail"
    assert stored_thumbnail.content == thumbnail.content
    assert cached_thumbnail.status_code == 304
    assert cached_thumbnail.content == b""
    assert thumbnail_generation_calls == [b"png-bytes"]


def test_history_image_edit_snapshot_and_delete_routes(
    history_repository_with_record: HistoryRepository,
) -> None:
    assert asyncio.run(history_repository_with_record.save_image_thumbnail(
        user_id=1,
        history_id=1,
        image_id=1,
        mime_type="image/webp",
        width=1,
        height=1,
        data=b"thumbnail",
    ))
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
        "output_format": None,
        "background": None,
        "output_compression": None,
            "moderation": None,
            "view_label": None,
            "references": [],
    }
    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert asyncio.run(
        history_repository_with_record.get_image_thumbnail(1, 1, 1)
    ) is None


def test_history_generation_slot_delete_route_only_removes_requested_slot(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "delete-generation-slot-api.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    repository = HistoryRepository(database_path)

    async def create_history() -> tuple[int, int]:
        history_id = await repository.create(
            user_id=1,
            kind="generate",
            prompt="生成两张",
            provider="compatible",
            model="custom-model",
            detail="auto",
            image_count=2,
        )
        batch_id = await repository.latest_generation_batch_id(
            user_id=1,
            history_id=history_id,
        )
        return history_id, batch_id

    history_id, batch_id = asyncio.run(create_history())
    app.dependency_overrides[get_history_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            deleted = client.delete(
                f"/api/history/{history_id}/batches/{batch_id}/slots/0"
            )
            detail = client.get(f"/api/history/{history_id}")
            missing = client.delete(
                f"/api/history/{history_id}/batches/{batch_id}/slots/2"
            )
    finally:
        app.dependency_overrides.clear()

    assert deleted.status_code == 204
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "generation_slot_not_found"
    assert detail.status_code == 200
    assert detail.json()["batches"][0]["deleted_positions"] == [0]


def test_history_generation_slot_cancel_route_only_cancels_requested_slot(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cancel-generation-slot-api.db"
    asyncio.run(initialize_database(database_path))
    asyncio.run(UserRepository(database_path).create("alice", hash_password("secret6")))
    repository = HistoryRepository(database_path)

    async def create_history() -> tuple[int, int]:
        history_id = await repository.create(
            user_id=1,
            kind="generate",
            prompt="生成两张",
            provider="compatible",
            model="custom-model",
            detail="auto",
            image_count=2,
        )
        batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
        return history_id, batch_id

    history_id, batch_id = asyncio.run(create_history())
    app.dependency_overrides[get_history_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            cancelled = client.post(
                f"/api/history/{history_id}/batches/{batch_id}/slots/1/cancel"
            )
            detail = client.get(f"/api/history/{history_id}")
            missing = client.post(
                f"/api/history/{history_id}/batches/{batch_id}/slots/2/cancel"
            )
    finally:
        app.dependency_overrides.clear()

    assert cancelled.status_code == 204
    assert missing.status_code == 409
    assert detail.status_code == 200
    assert detail.json()["batches"][0]["cancelled_positions"] == [1]


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
            thumbnail = client.get("/api/history/999/images/999/thumbnail?v=1")
    finally:
        app.dependency_overrides.clear()

    assert detail.status_code == 404
    assert detail.json()["error"]["code"] == "history_not_found"
    assert image.status_code == 404
    assert image.json()["error"]["code"] == "history_image_not_found"
    assert thumbnail.status_code == 404
    assert thumbnail.json()["error"]["code"] == "history_image_not_found"
