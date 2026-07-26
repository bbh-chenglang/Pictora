from pathlib import Path

import pytest
import pytest_asyncio

from app.database import initialize_database
from app.providers.base import ProviderAuthError
from app.repositories.history_repository import HistoryRepository
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.history_service import HistoryService


@pytest_asyncio.fixture
async def history_repository(tmp_path: Path) -> HistoryRepository:
    database_path = tmp_path / "history-service.db"
    await initialize_database(database_path)
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
    )
    summary = (await history_repository.list(limit=1))[0]
    detail = await history_repository.get(summary.id)
    assert detail is not None
    blob = await history_repository.get_image(detail.id, detail.images[0].id)

    assert response.images[0].base64_data == "cG5nLWJ5dGVz"
    assert blob is not None
    assert blob.data == b"png-bytes"
    assert blob.mime_type == "image/png"


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
    )
    detail = await history_repository.get((await history_repository.list(limit=1))[0].id)
    assert detail is not None
    blob = await history_repository.get_image(detail.id, detail.images[0].id)

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
        image_service=FakeImageService(),
        provider="compatible",
        model="vision-model",
        prompt="描述",
        detail="auto",
        image_bytes=b"jpeg",
        content_type="image/jpeg",
        filename="reference.jpg",
    )

    detail = await history_repository.get((await history_repository.list(limit=1))[0].id)

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
        )

    detail = await history_repository.get((await history_repository.list(limit=1))[0].id)

    assert detail is not None
    assert detail.status == "failed"
    assert detail.error_code == "provider_auth"
