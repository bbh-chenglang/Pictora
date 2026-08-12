import asyncio
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from app.database import initialize_database
from app.auth import hash_password
from app.providers.base import ProviderAuthError, ProviderRequestError
from app.repositories.history_repository import HistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import GenerateRequest, GenerateResponse, ReferenceImage
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

    async def generate(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImage | None = None,
    ) -> GenerateResponse:
        self.reference_image = reference_image
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


class BlockingImageService(FakeImageService):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def generate(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImage | None = None,
    ) -> GenerateResponse:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_generation_can_be_created_and_executed_as_separate_task(
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
    request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="异步生成",
    )

    task_id = await service.create_generation(request, user_id=1)
    pending = await history_repository.get(1, task_id)

    assert pending is not None
    assert pending.status == "pending"
    assert pending.images == []

    await service.execute_generation(task_id, request, image_service, user_id=1)
    completed = await history_repository.get(1, task_id)

    assert completed is not None
    assert completed.status == "completed"
    assert [image.role for image in completed.images] == ["generated"]


@pytest.mark.asyncio
async def test_generation_reuses_a_conversation_and_appends_new_images(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data="Zmlyc3Q=")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    first_request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="第一轮",
    )
    first_reference = ReferenceImage(
        data=b"first-reference",
        content_type="image/jpeg",
        filename="first.jpg",
    )

    conversation_id = await service.create_generation(
        first_request,
        user_id=1,
        reference_image=first_reference,
    )
    await service.execute_generation(
        conversation_id,
        first_request,
        image_service,
        user_id=1,
        reference_image=first_reference,
    )

    image_service.generate_response = GenerateResponse(
        provider="compatible",
        model="custom-model",
        images=[ImageResult(base64_data="c2Vjb25k")],
    )
    second_request = GenerateRequest(
        conversation_id=conversation_id,
        provider="compatible",
        model="custom-model",
        prompt="第二轮",
    )
    second_reference = ReferenceImage(
        data=b"second-reference",
        content_type="image/png",
        filename="second.png",
    )
    reused_id = await service.create_generation(
        second_request,
        user_id=1,
        reference_image=second_reference,
    )
    pending = await history_repository.get(1, conversation_id)

    assert reused_id == conversation_id
    assert pending is not None
    assert pending.status == "pending"
    assert [image.filename for image in pending.images if image.role == "reference"] == ["second.png"]
    assert len([image for image in pending.images if image.role == "generated"]) == 1

    await service.execute_generation(
        conversation_id,
        second_request,
        image_service,
        user_id=1,
        reference_image=second_reference,
    )
    completed = await history_repository.get(1, conversation_id)
    summaries = await history_repository.list(user_id=1, limit=20)

    assert completed is not None
    assert completed.prompt == "第二轮"
    assert [image.position for image in completed.images if image.role == "generated"] == [0, 1]
    assert len(summaries) == 1


@pytest.mark.asyncio
async def test_generation_queues_multiple_batches_in_the_same_pending_conversation(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data="Zmlyc3Q=")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    first_request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="第一批",
    )
    history_id, first_batch_id = await service.create_generation(
        first_request,
        user_id=1,
        include_batch_id=True,
    )
    second_request = GenerateRequest(
        conversation_id=history_id,
        provider="compatible",
        model="custom-model",
        prompt="第二批",
    )
    reused_id, second_batch_id = await service.create_generation(
        second_request,
        user_id=1,
        include_batch_id=True,
    )

    assert reused_id == history_id
    assert second_batch_id != first_batch_id

    await service.execute_generation(
        history_id,
        first_request,
        image_service,
        user_id=1,
        batch_id=first_batch_id,
    )
    first_batch = await history_repository.get_generation_batch(1, history_id, first_batch_id)
    queued_batch = await history_repository.get_generation_batch(1, history_id, second_batch_id)
    pending_conversation = await history_repository.get(1, history_id)

    assert first_batch is not None and first_batch.status == "completed"
    assert queued_batch is not None and queued_batch.status == "pending"
    assert pending_conversation is not None and pending_conversation.status == "pending"
    assert [image.batch_id for image in first_batch.images] == [first_batch_id]

    image_service.generate_response = GenerateResponse(
        provider="compatible",
        model="custom-model",
        images=[ImageResult(base64_data="c2Vjb25k")],
    )
    await service.execute_generation(
        history_id,
        second_request,
        image_service,
        user_id=1,
        batch_id=second_batch_id,
    )
    completed_batch = await history_repository.get_generation_batch(1, history_id, second_batch_id)
    completed_conversation = await history_repository.get(1, history_id)

    assert completed_batch is not None and completed_batch.status == "completed"
    assert completed_conversation is not None and completed_conversation.status == "completed"
    assert [image.batch_id for image in completed_batch.images] == [second_batch_id]


@pytest.mark.asyncio
async def test_each_generated_image_keeps_its_batch_snapshot_and_can_be_deleted(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="gemini",
            model="gemini-first",
            images=[ImageResult(base64_data="Zmlyc3Q=")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    first_request = GenerateRequest(
        provider="gemini",
        model="gemini-first",
        prompt="第一轮提示词",
        detail="high",
        count=2,
        size="16:9",
        aspect_ratio="16:9",
        resolution="4K",
    )
    first_reference = ReferenceImage(
        data=b"person",
        content_type="image/jpeg",
        filename="person.jpg",
        category="person",
    )
    history_id = await service.create_generation(
        first_request,
        user_id=1,
        reference_image=first_reference,
    )
    await service.execute_generation(
        history_id,
        first_request,
        image_service,
        user_id=1,
        reference_image=first_reference,
    )

    image_service.generate_response = GenerateResponse(
        provider="gemini",
        model="gemini-second",
        images=[ImageResult(base64_data="c2Vjb25k")],
    )
    second_request = GenerateRequest(
        conversation_id=history_id,
        provider="gemini",
        model="gemini-second",
        prompt="第二轮提示词",
        detail="low",
        count=1,
        size="2:3",
        aspect_ratio="2:3",
        resolution="1K",
    )
    second_reference = ReferenceImage(
        data=b"room",
        content_type="image/png",
        filename="room.png",
        category="environment",
    )
    await service.create_generation(
        second_request,
        user_id=1,
        reference_image=second_reference,
    )
    await service.execute_generation(
        history_id,
        second_request,
        image_service,
        user_id=1,
        reference_image=second_reference,
    )

    detail = await history_repository.get(1, history_id)
    assert detail is not None
    generated_images = [image for image in detail.images if image.role == "generated"]
    assert len(generated_images) == 2
    first_snapshot = await history_repository.get_image_edit_snapshot(
        1, history_id, generated_images[0].id
    )
    second_snapshot = await history_repository.get_image_edit_snapshot(
        1, history_id, generated_images[1].id
    )

    assert first_snapshot is not None
    assert first_snapshot.prompt == "第一轮提示词"
    assert first_snapshot.model == "gemini-first"
    assert first_snapshot.detail == "auto"
    assert first_snapshot.image_count == 2
    assert first_snapshot.size == "16:9"
    assert first_snapshot.resolution is None
    assert [(reference.category, reference.filename) for reference in first_snapshot.references] == [
        ("person", "person.jpg")
    ]
    assert second_snapshot is not None
    assert second_snapshot.prompt == "第二轮提示词"
    assert second_snapshot.model == "gemini-second"
    assert second_snapshot.detail == "auto"
    assert second_snapshot.image_count == 1
    assert [(reference.category, reference.filename) for reference in second_snapshot.references] == [
        ("environment", "room.png")
    ]

    async with aiosqlite.connect(history_repository.database_path) as connection:
        batch_count = (await (await connection.execute(
            "SELECT COUNT(*) FROM generation_batches WHERE history_id = ?", (history_id,)
        )).fetchone())[0]
    assert batch_count == 2
    assert await history_repository.get_image_edit_snapshot(
        2, history_id, generated_images[0].id
    ) is None
    assert not await history_repository.delete_generated_image(
        2, history_id, generated_images[0].id
    )

    assert await history_repository.delete_generated_image(
        1, history_id, generated_images[0].id
    )
    remaining = await history_repository.get(1, history_id)
    assert remaining is not None
    assert [image.id for image in remaining.images if image.role == "generated"] == [
        generated_images[1].id
    ]
    assert [image.filename for image in remaining.images if image.role == "reference"] == [
        "room.png"
    ]


@pytest.mark.asyncio
async def test_pending_generation_is_failed_during_restart_recovery(
    history_repository: HistoryRepository,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    task_id = await service.create_generation(
        GenerateRequest(
            provider="compatible",
            model="custom-model",
            prompt="等待重启",
        ),
        user_id=1,
    )

    changed = await history_repository.fail_pending_generations()
    detail = await history_repository.get(1, task_id)

    assert changed == 1
    assert detail is not None
    assert detail.status == "failed"
    assert detail.error_code == "generation_interrupted"


@pytest.mark.asyncio
async def test_cancelling_background_generation_marks_task_failed(
    history_repository: HistoryRepository,
) -> None:
    image_service = BlockingImageService()
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="取消测试",
    )
    task_id = await service.create_generation(request, user_id=1)
    operation = asyncio.create_task(
        service.execute_generation(task_id, request, image_service, user_id=1)
    )
    await image_service.started.wait()

    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    detail = await history_repository.get(1, task_id)

    assert detail is not None
    assert detail.status == "failed"
    assert detail.error_code == "generation_cancelled"


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
async def test_generation_history_preserves_data_url_image_type(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="gemini",
            model="gemini-image",
            images=[ImageResult(base64_data="data:image/jpeg;base64,anBlZy1ieXRlcw==")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-image",
            prompt="JPEG 图片",
        ),
        image_service,
        1,
    )
    detail = await history_repository.get(
        1, (await history_repository.list(user_id=1, limit=1))[0].id
    )
    assert detail is not None
    blob = await history_repository.get_image(1, detail.id, detail.images[0].id)

    assert blob is not None
    assert blob.data == b"jpeg-bytes"
    assert blob.mime_type == "image/jpeg"


@pytest.mark.asyncio
async def test_generation_history_preserves_response_image_type(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="grok",
            model="grok-imagine-image",
            images=[ImageResult(base64_data="d2VicC1ieXRlcw==", mime_type="image/webp")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    await service.generate(
        GenerateRequest(
            provider="grok",
            model="grok-imagine-image",
            prompt="WebP 图片",
            aspect_ratio="20:9",
            resolution="2K",
        ),
        image_service,
        1,
    )
    detail = await history_repository.get(
        1, (await history_repository.list(user_id=1, limit=1))[0].id
    )
    assert detail is not None
    blob = await history_repository.get_image(1, detail.id, detail.images[0].id)

    assert blob is not None
    assert blob.data == b"webp-bytes"
    assert blob.mime_type == "image/webp"
    assert detail.size == "20:9"
    assert detail.resolution == "2K"


@pytest.mark.asyncio
async def test_generation_history_stores_and_forwards_reference_image(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="gemini",
            model="gemini-image",
            images=[ImageResult(base64_data="cG5nLWJ5dGVz")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    reference = ReferenceImage(
        data=b"reference-bytes",
        content_type="image/jpeg",
        filename="room.jpg",
    )

    await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-image",
            prompt="根据参考图调整光线",
        ),
        image_service,
        1,
        reference_image=reference,
    )

    detail = await history_repository.get(
        1, (await history_repository.list(user_id=1, limit=1))[0].id
    )
    assert image_service.reference_image == reference
    assert detail is not None
    assert [image.role for image in detail.images] == ["reference", "generated"]
    reference_blob = await history_repository.get_image(1, detail.id, detail.images[0].id)
    assert reference_blob is not None
    assert reference_blob.data == b"reference-bytes"
    assert reference_blob.filename == "room.jpg"


@pytest.mark.asyncio
async def test_generation_history_stores_multiple_reference_images_in_order(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService()
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    references = [
        ReferenceImage(data=b"room", content_type="image/jpeg", filename="room.jpg"),
        ReferenceImage(data=b"material", content_type="image/png", filename="material.png"),
    ]

    await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-image",
            prompt="融合两张参考图",
        ),
        image_service,
        1,
        reference_image=references,
    )

    detail = await history_repository.get(
        1, (await history_repository.list(user_id=1, limit=1))[0].id
    )
    assert image_service.reference_image == references
    assert detail is not None
    stored_references = [image for image in detail.images if image.role == "reference"]
    assert [image.filename for image in stored_references] == ["room.jpg", "material.png"]
    assert [image.position for image in stored_references] == [0, 1]


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
async def test_generation_keeps_upstream_image_without_cropping(
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
            prompt="构图测试",
            aspect_ratio="16:9",
            resolution="4K",
        ),
        image_service,
        1,
    )
    history_id = (await history_repository.list(user_id=1, limit=1))[0].id
    detail = await history_repository.get(1, history_id)
    assert detail is not None
    blob = await history_repository.get_image(1, detail.id, detail.images[0].id)

    assert blob is not None
    assert blob.data == b"png-bytes"
    assert response.images[0].base64_data == "cG5nLWJ5dGVz"
    assert response.images[0].url is None


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
async def test_provider_request_failure_preserves_safe_upstream_detail(
    history_repository: HistoryRepository,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    error = ProviderRequestError(
        status_code=403,
        response_content=(
            b'{"error":{"message":"Grok account is not eligible; '
            b'API key: xai-secretvalue123"}}'
        ),
        content_type="application/json",
    )

    with pytest.raises(ProviderRequestError):
        await service.generate(
            GenerateRequest(
                provider="grok",
                model="grok-imagine-image",
                prompt="test",
            ),
            FailingImageService(error),
            1,
        )

    detail = await history_repository.get(
        1, (await history_repository.list(user_id=1, limit=1))[0].id
    )

    assert detail is not None
    assert detail.error_message == (
        "Provider request failed (HTTP 403): "
        "Grok account is not eligible; API key: [REDACTED]"
    )
    assert "xai-secretvalue123" not in detail.error_message


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
