import asyncio
import base64
from pathlib import Path

import aiosqlite
import pytest
import pytest_asyncio

from app.database import initialize_database
from app.auth import hash_password
from app.providers.base import ProviderAuthError, ProviderRequestError
from app.repositories.history_repository import (
    GenerationTaskNotRunnableError,
    HistoryRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.analyze import AnalyzeResponse
from app.schemas.common import ImageResult
from app.schemas.generate import (
    GenerateRequest,
    GenerateResponse,
    ImageGenerationFailure,
    ReferenceImage,
)
from app.services.history_service import HistoryService
from app.services import history_service as history_service_module


PNG_BYTES = b"\x89PNG\r\n\x1a\npng-bytes"
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode("ascii")
JPEG_BYTES = b"\xff\xd8\xffjpeg-bytes"
JPEG_BASE64 = base64.b64encode(JPEG_BYTES).decode("ascii")
WEBP_BYTES = b"RIFF\x04\x00\x00\x00WEBPwebp-bytes"
WEBP_BASE64 = base64.b64encode(WEBP_BYTES).decode("ascii")
GIF_BYTES = b"GIF89agif-bytes"


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
        *,
        on_image=None,
        should_skip=None,
    ) -> GenerateResponse:
        self.reference_image = reference_image
        positioned_images = [
            image
            if image.generation_position is not None
            else image.model_copy(update={"generation_position": index})
            for index, image in enumerate(self.generate_response.images)
        ]
        response = self.generate_response.model_copy(update={"images": positioned_images})
        if on_image is not None:
            for image in response.images:
                await on_image(image)
        return response

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
    content = b"RIFF\x04\x00\x00\x00WEBPVP8 "
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

    async def generate(self, request: GenerateRequest, *, on_image=None, should_skip=None) -> GenerateResponse:
        raise self.error


class BlockingImageService(FakeImageService):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()

    async def generate(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImage | None = None,
        *,
        on_image=None,
        should_skip=None,
    ) -> GenerateResponse:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class ReleasableImageService(FakeImageService):
    def __init__(self, response: GenerateResponse) -> None:
        super().__init__(response)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(
        self,
        request: GenerateRequest,
        reference_image: ReferenceImage | None = None,
        *,
        on_image=None,
        should_skip=None,
    ) -> GenerateResponse:
        self.started.set()
        await self.release.wait()
        return self.generate_response


@pytest.mark.asyncio
async def test_generation_can_be_created_and_executed_as_separate_task(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data=PNG_BASE64)],
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
async def test_generation_persists_each_image_before_the_batch_finishes(
    history_repository: HistoryRepository,
) -> None:
    class ProgressiveImageService:
        def __init__(self) -> None:
            self.first_image_saved = asyncio.Event()
            self.release_second_image = asyncio.Event()

        async def generate(self, request: GenerateRequest, *, on_image=None, should_skip=None) -> GenerateResponse:
            assert on_image is not None
            first = ImageResult(base64_data=PNG_BASE64, generation_position=0)
            second = ImageResult(
                base64_data=JPEG_BASE64,
                mime_type="image/jpeg",
                generation_position=1,
            )
            await on_image(first)
            self.first_image_saved.set()
            await self.release_second_image.wait()
            await on_image(second)
            return GenerateResponse(
                provider=request.provider,
                model=request.model,
                images=[first, second],
            )

    image_service = ProgressiveImageService()
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="逐张展示",
        count=2,
    )
    history_id, batch_id, task_id = await service.create_generation(
        request,
        user_id=1,
        include_batch_id=True,
        include_task_id=True,
    )
    execution = asyncio.create_task(service.execute_generation(
        history_id,
        request,
        image_service,
        user_id=1,
        batch_id=batch_id,
        task_id=task_id,
        worker_id="worker-progressive",
    ))

    await asyncio.wait_for(image_service.first_image_saved.wait(), timeout=1)
    running_task = await history_repository.get_generation_task(1, task_id)
    partial_batch = await history_repository.get_generation_batch(1, history_id, batch_id)

    assert running_task is not None and running_task["status"] == "running"
    assert running_task["generated_count"] == 1
    assert [image.batch_position for image in running_task["images"]] == [0]
    assert partial_batch is not None and partial_batch.status == "pending"
    assert partial_batch.generated_count == 1
    assert [image.batch_position for image in partial_batch.images] == [0]

    image_service.release_second_image.set()
    await execution
    completed_batch = await history_repository.get_generation_batch(1, history_id, batch_id)
    assert completed_batch is not None and completed_batch.status == "completed"
    assert completed_batch.generated_count == 2
    assert [image.batch_position for image in completed_batch.images] == [0, 1]


@pytest.mark.asyncio
async def test_partial_generation_fails_only_missing_slots_and_keeps_images(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data=PNG_BASE64)],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="请求两张",
        count=2,
    )
    history_id, batch_id, task_id = await service.create_generation(
        request,
        user_id=1,
        include_batch_id=True,
        include_task_id=True,
    )

    await service.execute_generation(
        history_id,
        request,
        image_service,
        user_id=1,
        batch_id=batch_id,
        task_id=task_id,
        worker_id="worker-partial",
    )

    task = await history_repository.get_generation_task(1, task_id)
    batch = await history_repository.get_generation_batch(1, history_id, batch_id)
    detail = await history_repository.get(1, history_id)
    assert task is not None and task["status"] == "failed"
    assert task["error_code"] == "partial_generation"
    assert batch is not None and batch.status == "failed"
    assert batch.generated_count == 1
    assert len(batch.images) == 1
    assert detail is not None and detail.status == "failed"


@pytest.mark.asyncio
async def test_partial_generation_preserves_original_slot_and_failure_reason(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="gemini",
            model="gemini-image",
            images=[
                ImageResult(
                    base64_data=PNG_BASE64,
                    generation_position=1,
                )
            ],
            failures=[
                ImageGenerationFailure(
                    position=0,
                    error_code="provider_request",
                    error_message="Provider request failed (HTTP 502)",
                )
            ],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    request = GenerateRequest(
        provider="gemini",
        model="gemini-image",
        prompt="请求两张",
        count=2,
    )
    history_id, batch_id, task_id = await service.create_generation(
        request,
        user_id=1,
        include_batch_id=True,
        include_task_id=True,
    )

    await service.execute_generation(
        history_id,
        request,
        image_service,
        user_id=1,
        batch_id=batch_id,
        task_id=task_id,
        worker_id="worker-partial-retry",
    )

    batch = await history_repository.get_generation_batch(1, history_id, batch_id)
    assert batch is not None
    assert batch.status == "failed"
    assert batch.generated_count == 1
    assert [image.batch_position for image in batch.images] == [1]
    assert "HTTP 502" in (batch.error_message or "")


@pytest.mark.asyncio
async def test_late_image_materialization_failure_keeps_already_saved_images(
    history_repository: HistoryRepository,
) -> None:
    async def private_resolver(_: str, __: int) -> list[str]:
        return ["127.0.0.1"]

    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[
                ImageResult(base64_data=PNG_BASE64),
                ImageResult(url="https://private.example/second.png"),
            ],
        )
    )
    service = HistoryService(
        history_repository,
        http_client=FakeHttpClient(),
        host_resolver=private_resolver,
    )
    request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="保留第一张",
        count=2,
    )
    history_id, batch_id, task_id = await service.create_generation(
        request,
        user_id=1,
        include_batch_id=True,
        include_task_id=True,
    )

    with pytest.raises(ValueError, match="non-public"):
        await service.execute_generation(
            history_id,
            request,
            image_service,
            user_id=1,
            batch_id=batch_id,
            task_id=task_id,
            worker_id="worker-materialize",
        )

    batch = await history_repository.get_generation_batch(1, history_id, batch_id)
    assert batch is not None and batch.status == "failed"
    assert batch.generated_count == 1
    assert len(batch.images) == 1


@pytest.mark.asyncio
async def test_second_worker_cannot_fail_or_persist_an_owned_generation(
    history_repository: HistoryRepository,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="跨 worker 保护",
    )
    history_id, batch_id, task_id = await service.create_generation(
        request,
        user_id=1,
        include_batch_id=True,
        include_task_id=True,
    )
    assert await history_repository.mark_generation_task_running(
        task_id,
        1,
        worker_id="worker-a",
    )

    with pytest.raises(GenerationTaskNotRunnableError):
        await service.execute_generation(
            history_id,
            request,
            FakeImageService(
                GenerateResponse(
                    provider="compatible",
                    model="custom-model",
                    images=[ImageResult(base64_data=PNG_BASE64)],
                )
            ),
            user_id=1,
            batch_id=batch_id,
            task_id=task_id,
            worker_id="worker-b",
        )

    task = await history_repository.get_generation_task(1, task_id)
    batch = await history_repository.get_generation_batch(1, history_id, batch_id)
    detail = await history_repository.get(1, history_id)
    assert task is not None and task["status"] == "running"
    assert batch is not None and batch.status == "pending"
    assert detail is not None and detail.status == "pending"
    assert detail.images == []


@pytest.mark.asyncio
async def test_cancelled_remote_task_does_not_persist_provider_result(
    history_repository: HistoryRepository,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    image_service = ReleasableImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data=PNG_BASE64)],
        )
    )
    request = GenerateRequest(
        provider="compatible",
        model="custom-model",
        prompt="跨 worker 取消",
    )
    history_id, batch_id, task_id = await service.create_generation(
        request,
        user_id=1,
        include_batch_id=True,
        include_task_id=True,
    )
    operation = asyncio.create_task(
        service.execute_generation(
            history_id,
            request,
            image_service,
            user_id=1,
            batch_id=batch_id,
            task_id=task_id,
            worker_id="worker-a",
        )
    )
    await image_service.started.wait()
    assert await history_repository.cancel_generation_task(task_id, 1)
    image_service.release.set()

    with pytest.raises(GenerationTaskNotRunnableError):
        await operation

    task = await history_repository.get_generation_task(1, task_id)
    batch = await history_repository.get_generation_batch(1, history_id, batch_id)
    detail = await history_repository.get(1, history_id)
    assert task is not None and task["status"] == "cancelled"
    assert batch is not None and batch.status == "failed"
    assert detail is not None and detail.status == "failed"
    assert detail.images == []


@pytest.mark.asyncio
async def test_generation_reuses_a_conversation_and_appends_new_images(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data=PNG_BASE64)],
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
        images=[ImageResult(base64_data=PNG_BASE64)],
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
async def test_generation_runs_multiple_batches_in_the_same_pending_conversation(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data=PNG_BASE64)],
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
    _, second_batch_id = await service.create_generation(
        second_request,
        user_id=1,
        include_batch_id=True,
    )

    await service.execute_generation(
        history_id,
        second_request,
        image_service,
        user_id=1,
        batch_id=second_batch_id,
    )
    while_first_runs = await history_repository.get(1, history_id)
    assert while_first_runs is not None and while_first_runs.status == "pending"

    await service.execute_generation(
        history_id,
        first_request,
        image_service,
        user_id=1,
        batch_id=first_batch_id,
    )
    first_batch = await history_repository.get_generation_batch(1, history_id, first_batch_id)
    second_batch = await history_repository.get_generation_batch(1, history_id, second_batch_id)
    completed_conversation = await history_repository.get(1, history_id)

    assert first_batch is not None and first_batch.status == "completed"
    assert second_batch is not None and second_batch.status == "completed"
    assert completed_conversation is not None and completed_conversation.status == "completed"
    assert completed_conversation.prompt == "第二批"
    assert len(completed_conversation.batches) == 2
    assert {image.batch_id for image in completed_conversation.images} == {
        first_batch_id,
        second_batch_id,
    }


@pytest.mark.asyncio
async def test_each_generated_image_keeps_its_batch_snapshot_and_can_be_deleted(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="gemini",
            model="gemini-first",
            images=[ImageResult(base64_data=PNG_BASE64)],
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
        images=[ImageResult(base64_data=PNG_BASE64)],
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
    assert first_snapshot.detail == "high"
    assert first_snapshot.image_count == 2
    assert first_snapshot.size == "16:9"
    assert first_snapshot.resolution == "4K"
    assert [(reference.category, reference.filename) for reference in first_snapshot.references] == [
        ("person", "person.jpg")
    ]
    assert second_snapshot is not None
    assert second_snapshot.prompt == "第二轮提示词"
    assert second_snapshot.model == "gemini-second"
    assert second_snapshot.detail == "low"
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

    async with aiosqlite.connect(history_repository.database_path) as connection:
        await connection.execute(
            "UPDATE generation_batches SET created_at = datetime('now', '-5 minutes') WHERE history_id = ?",
            (task_id,),
        )
        await connection.commit()

    await history_repository.fail_stale_generation_tasks(stale_after_seconds=120)
    detail = await history_repository.get(1, task_id)

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
            images=[ImageResult(base64_data=PNG_BASE64)],
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

    assert response.images[0].base64_data == PNG_BASE64
    assert blob is not None
    assert blob.data == PNG_BYTES
    assert blob.mime_type == "image/png"


@pytest.mark.asyncio
async def test_generation_history_rejects_oversized_base64_before_decoding(
    history_repository: HistoryRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(history_service_module, "MAX_REMOTE_IMAGE_BYTES", 8)
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    with pytest.raises(ValueError, match="20 MB"):
        await service._materialize_image(
            ImageResult(base64_data="MTIzNDU2Nzg5")
        )


@pytest.mark.asyncio
async def test_generation_history_normalizes_mismatched_base64_image_type(
    history_repository: HistoryRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    with caplog.at_level("WARNING", logger="app.services.history_service"):
        materialized = await service._materialize_image(
            ImageResult(base64_data=f"data:image/jpeg;base64,{PNG_BASE64}")
        )

    assert materialized == ("image/png", PNG_BYTES)
    assert "step=base64_image_type_normalized" in caplog.text
    assert "declared_type=image/jpeg" in caplog.text
    assert "detected_type=image/png" in caplog.text
    assert f"byte_count={len(PNG_BYTES)}" in caplog.text
    assert f"signature_hex={PNG_BYTES[:12].hex()}" in caplog.text
    assert PNG_BASE64 not in caplog.text


@pytest.mark.asyncio
async def test_generation_history_diagnoses_unknown_base64_image_type(
    history_repository: HistoryRepository,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    unknown_bytes = b"not-an-image-payload"
    encoded = base64.b64encode(unknown_bytes).decode("ascii")

    with pytest.raises(ValueError) as caught:
        await service._materialize_image(
            ImageResult(base64_data=encoded, mime_type="image/png")
        )

    diagnostic = str(caught.value)
    assert "declared=image/png" in diagnostic
    assert "detected=unknown" in diagnostic
    assert f"bytes={len(unknown_bytes)}" in diagnostic
    assert f"signature={unknown_bytes[:12].hex()}" in diagnostic
    assert encoded not in diagnostic


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_bytes", "mime_type"),
    [
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (WEBP_BYTES, "image/webp"),
        (GIF_BYTES, "image/gif"),
    ],
)
async def test_generation_history_accepts_supported_base64_image_types(
    history_repository: HistoryRepository,
    image_bytes: bytes,
    mime_type: str,
) -> None:
    service = HistoryService(history_repository, http_client=FakeHttpClient())
    encoded = base64.b64encode(image_bytes).decode("ascii")

    materialized = await service._materialize_image(
        ImageResult(base64_data=encoded, mime_type=mime_type)
    )

    assert materialized == (mime_type, image_bytes)


@pytest.mark.asyncio
async def test_generation_history_persists_normalized_base64_image_type(
    history_repository: HistoryRepository,
    caplog: pytest.LogCaptureFixture,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="gemini",
            model="gemini-image",
            images=[
                ImageResult(base64_data=f"data:image/png;base64,{JPEG_BASE64}")
            ],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    with caplog.at_level("WARNING", logger="app.services.history_service"):
        await service.generate(
            GenerateRequest(
                provider="gemini",
                model="gemini-image",
                prompt="诊断图片格式",
            ),
            image_service,
            1,
        )

    detail = await history_repository.get(
        1, (await history_repository.list(user_id=1, limit=1))[0].id
    )
    assert detail is not None
    assert detail.status == "completed"
    assert detail.error_code is None
    blob = await history_repository.get_image(1, detail.id, detail.images[0].id)
    assert blob is not None
    assert blob.mime_type == "image/jpeg"
    assert blob.data == JPEG_BYTES
    assert "declared_type=image/png" in caplog.text
    assert "detected_type=image/jpeg" in caplog.text
    assert JPEG_BASE64 not in caplog.text


@pytest.mark.asyncio
async def test_reference_storage_failure_fails_generation_batch(
    history_repository: HistoryRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_reference_storage(**_kwargs) -> None:
        raise aiosqlite.IntegrityError("write failed")

    monkeypatch.setattr(history_repository, "add_reference_images", fail_reference_storage)
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    with pytest.raises(aiosqlite.IntegrityError):
        await service.create_generation(
            GenerateRequest(provider="compatible", model="custom-model", prompt="失败测试"),
            user_id=1,
            reference_image=ReferenceImage(
                data=b"reference",
                content_type="image/png",
                filename="reference.png",
            ),
        )

    summary = (await history_repository.list(user_id=1, limit=1))[0]
    detail = await history_repository.get(1, summary.id)
    assert detail is not None
    assert detail.status == "failed"
    assert detail.error_code == "internal_error"
    assert detail.batches[0].status == "failed"
    assert detail.images == []


@pytest.mark.asyncio
async def test_generation_history_preserves_data_url_image_type(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="gemini",
            model="gemini-image",
            images=[ImageResult(base64_data=f"data:image/jpeg;base64,{JPEG_BASE64}")],
        )
    )
    service = HistoryService(history_repository, http_client=FakeHttpClient())

    await service.generate(
        GenerateRequest(
            provider="gemini",
            model="gemini-image",
            prompt="JPEG 图片",
            aspect_ratio="16:9",
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
    assert blob.data == JPEG_BYTES
    assert blob.mime_type == "image/jpeg"
    assert detail.size == "16:9"


@pytest.mark.asyncio
async def test_generation_history_preserves_response_image_type(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="grok",
            model="grok-imagine-image",
            images=[ImageResult(base64_data=WEBP_BASE64, mime_type="image/webp")],
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
    assert blob.data == WEBP_BYTES
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
            images=[ImageResult(base64_data=PNG_BASE64)],
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
    async def public_resolver(hostname: str, port: int) -> list[str]:
        assert (hostname, port) == ("cdn.example", 443)
        return ["93.184.216.34"]

    service = HistoryService(
        history_repository,
        http_client=http_client,
        host_resolver=public_resolver,
    )

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
    assert blob.data == FakeHttpResponse.content
    assert blob.mime_type == "image/webp"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "addresses", "message"),
    [
        ("http://cdn.example/image.png", ["93.184.216.34"], "public HTTPS"),
        ("https://cdn.example/image.png", ["127.0.0.1"], "non-public"),
        ("https://cdn.example/image.png", ["169.254.169.254"], "non-public"),
    ],
)
async def test_remote_image_rejects_insecure_or_private_sources(
    history_repository: HistoryRepository,
    url: str,
    addresses: list[str],
    message: str,
) -> None:
    async def resolver(_: str, __: int) -> list[str]:
        return addresses

    client = FakeHttpClient()
    service = HistoryService(
        history_repository,
        http_client=client,
        host_resolver=resolver,
    )
    with pytest.raises(ValueError, match=message):
        await service._materialize_image(ImageResult(url=url))
    assert client.requested_urls == []


@pytest.mark.asyncio
async def test_remote_image_rejects_redirects_oversized_and_fake_images(
    history_repository: HistoryRepository,
) -> None:
    async def resolver(_: str, __: int) -> list[str]:
        return ["93.184.216.34"]

    class Response:
        def __init__(self, status: int, headers: dict[str, str], content: bytes) -> None:
            self.status_code = status
            self.headers = headers
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class Client:
        def __init__(self, response: Response) -> None:
            self.response = response

        async def get(self, _: str) -> Response:
            return self.response

    cases = [
        (Response(302, {"Location": "https://other.example/image.png"}, b""), "redirects"),
        (Response(200, {"Content-Type": "image/png", "Content-Length": str(21 * 1024 * 1024)}, b""), "20 MB"),
        (Response(200, {"Content-Type": "text/html"}, b"<html>not an image</html>"), "invalid image type"),
    ]
    for response, message in cases:
        service = HistoryService(
            history_repository,
            http_client=Client(response),
            host_resolver=resolver,
        )
        with pytest.raises(ValueError, match=message):
            await service._materialize_image(ImageResult(url="https://cdn.example/image.png"))


@pytest.mark.asyncio
async def test_generation_keeps_upstream_image_without_cropping(
    history_repository: HistoryRepository,
) -> None:
    image_service = FakeImageService(
        GenerateResponse(
            provider="compatible",
            model="custom-model",
            images=[ImageResult(base64_data=PNG_BASE64)],
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
    assert blob.data == PNG_BYTES
    assert response.images[0].base64_data == PNG_BASE64
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
            images=[ImageResult(base64_data=PNG_BASE64)],
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
