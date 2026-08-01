from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from app.database import initialize_database
from app.auth import hash_password
from app.providers.base import ProviderAuthError
from app.repositories.history_repository import HistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.history_service import HistoryService


@pytest_asyncio.fixture
async def history_repository(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "history-service.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    return HistoryRepository(database_path)


class FakeImageService:
    def __init__(self, generate_response: GenerateResponse | None = None) -> None:
        self.generate_response = generate_response or GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[],
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        return self.generate_response

    async def analyze(
        self,
        provider,
        model,
        prompt,
        detail,
        image_bytes,
        content_type,
    ) -> AnalyzeResponse:
        return AnalyzeResponse(
            provider=provider,
            model=model,
            text="分析结果",
        )


class FakeHttpResponse:
    status_code = 200
    content = b"downloaded-image"
    headers = {"Content-Type": "image/webp; charset=binary"}

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self) -> None:
        self.requested_urls: list[str] = []

    async def get(self, url: str) -> FakeHttpResponse:
        self.requested_urls.append(url)
        return FakeHttpResponse()


class FailingImageService(FakeImageService):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        raise self.error


@pytest.mark.asyncio
async def test_generation_history_decodes_base64_into_blob(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data="cG5nLWJ5dGVz")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    response = await service.generate(
        GenerateRequest(
            provider="compatible",
            model="custom-model",
            prompt="苹果",
        ),
        image_service,
        1,
    )
    summary = (await history_repository.list(user_id=1, limit=1))[0]
    detail = await history_repository.get(1, summary.id)
    assert detail is not None
    blob = await history_repository.get_image(1, detail.id, detail.images[0].id)

    assert response.images[0].base64_data == "cG5nLWJ5dGVz"
    assert blob is not None
    assert blob.data == b"png-bytes"
    assert blob.mime_type == "image/png"


@pytest.mark.asyncio
async def test_generation_names_empty_project_from_prompt(
    history_repository: HistoryRepository,
) -> None:
    async with aiosqlite.connect(history_repository.database_path) as connection:
        await connection.execute("UPDATE projects SET name = '   ' WHERE user_id = 1")
        await connection.commit()

    service = HistoryService(history_repository, http_client=FakeHttpClient())
    await service.generate(
        GenerateRequest(
            provider="compatible",
            model="custom-model",
            prompt="蓝色海面与晨光",
        ),
        FakeImageService(),
        1,
    )

    async with aiosqlite.connect(history_repository.database_path) as connection:
        cursor = await connection.execute("SELECT name FROM projects WHERE user_id = 1")
        assert (await cursor.fetchone())[0] == "蓝色海面与"


@pytest.mark.asyncio
async def test_generation_history_downloads_remote_images(
    history_repository: HistoryRepository,
) -> None:
    http_client = FakeHttpClient()
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(url="https://cdn.example/result.webp")],
        )
    )
    service = HistoryService(history_repository, http_client=http_client)

    await service.generate(
        GenerateRequest(
            provider="compatible",
            model="custom-model",
            prompt="海面",
        ),
        image_service,
        1,
    )
    detail = await history_repository.get(1, (await history_repository.list(user_id=1, limit=1))[0].id)
    assert detail is not None
    blob = await history_repository.get_image(1, detail.id, detail.images[0].id)

    assert http_client.requested_urls == ["https://cdn.example/result.webp"]
    assert blob is not None
    assert blob.data == b"downloaded-image"
    assert blob.mime_type == "image/webp"


@pytest.mark.asyncio
async def test_analysis_history_stores_reference_and_text(
    history_repository: HistoryRepository,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    result = await service.analyze(
        user_id=1,
        image_service=FakeImageService(),
        provider="compatible",
        model="vision-model",
        prompt="描述",
        detail="auto",
        image_bytes=b"jpeg",
        content_type="image/jpeg",
        filename="reference.jpg",
    )

    detail = await history_repository.get(1, (await history_repository.list(user_id=1, limit=1))[0].id)

    assert result.text == "分析结果"
    assert detail is not None
    assert detail.analysis_text == "分析结果"
    assert detail.images[0].role == "reference"


@pytest.mark.asyncio
async def test_provider_failure_marks_history_failed(
    history_repository: HistoryRepository,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    with pytest.raises(ProviderAuthError):
        await service.generate(
            GenerateRequest(
                provider="compatible",
                model="custom-model",
                prompt="苹果",
            ),
            FailingImageService(ProviderAuthError()),
            1,
        )

    detail = await history_repository.get(1, (await history_repository.list(user_id=1, limit=1))[0].id)

    assert detail is not None
    assert detail.status == "failed"
    assert detail.error_code == "provider_auth"


@pytest.mark.asyncio
async def test_generation_logs_timed_steps(
    history_repository: HistoryRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data="cG5nLWJ5dGVz")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    with caplog.at_level("INFO", logger="app.services.history_service"):
        await service.generate(
            GenerateRequest(
                provider="compatible",
                model="custom-model",
                prompt="timed generation",
            ),
            image_service,
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("step=generation_started" in message for message in messages)
    assert any("step=image_service_completed" in message for message in messages)
    assert any("step=image_materialize_completed" in message for message in messages)
    assert any("step=history_image_saved" in message for message in messages)
    assert any("step=generation_completed" in message for message in messages)
    assert all("generation_id=" in message for message in messages)
    assert all("duration_ms=" in message for message in messages)
