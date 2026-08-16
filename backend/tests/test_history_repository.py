from pathlib import Path

import aiosqlite
import pytest

from app.database import initialize_database
from app.auth import hash_password
from app.repositories.history_repository import HistoryRepository
from app.repositories.user_repository import UserRepository
from app.schemas.common import GenerationViewSpec


@pytest.mark.asyncio
async def test_history_repository_tracks_task_and_blob_images(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)

    history_id = await repository.create(
        user_id=1,
        kind="generate",
        prompt="画一个苹果",
        provider="compatible",
        model="custom-model",
        detail="high",
        image_count=1,
        size="1152x1536",
        resolution="2K",
    )
    await repository.add_image(
        user_id=1,
        history_id=history_id,
        role="generated",
        mime_type="image/png",
        filename="generated-1.png",
        position=0,
        data=b"png-bytes",
    )
    await repository.complete(history_id, elapsed_ms=1250)

    summaries = await repository.list(user_id=1, limit=20)
    detail = await repository.get(1, history_id)
    assert detail is not None
    image = await repository.get_image(1, history_id, detail.images[0].id)

    assert summaries[0].status == "completed"
    assert summaries[0].prompt == "画一个苹果"
    assert summaries[0].size == "1152x1536"
    assert summaries[0].resolution == "2K"
    assert detail.images[0].role == "generated"
    assert detail.images[0].batch_id is not None
    assert (
        detail.images[0].url
        == f"/api/history/{history_id}/images/{detail.images[0].id}"
    )
    assert image is not None
    assert image.data == b"png-bytes"


@pytest.mark.asyncio
async def test_history_repository_persists_views_and_restores_single_view_edit(tmp_path: Path) -> None:
    database_path = tmp_path / "multi-view-history.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)
    views = [
        GenerationViewSpec(key="person_front", label="正面", prompt="基础提示词\n\n正面要求"),
        GenerationViewSpec(key="person_back", label="背面", prompt="基础提示词\n\n背面要求"),
    ]
    history_id = await repository.create(
        user_id=1,
        kind="generate",
        prompt="基础提示词",
        provider="gemini",
        model="gemini-3.1-flash-image",
        detail="auto",
        image_count=2,
        views=views,
    )
    batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
    task_id = await repository.create_generation_task(user_id=1, history_id=history_id, batch_id=batch_id)
    image_id = await repository.add_image(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
        role="generated",
        mime_type="image/png",
        filename="back.png",
        position=0,
        batch_position=1,
        data=b"back",
    )

    detail = await repository.get(1, history_id)
    batch = await repository.get_generation_batch(1, history_id, batch_id)
    snapshot = await repository.get_image_edit_snapshot(1, history_id, int(image_id))
    task = await repository.get_generation_task(1, task_id)

    assert detail is not None and detail.batches[0].views == views
    assert batch is not None and batch.views == views
    assert task is not None and task["views"] == views
    assert snapshot is not None
    assert snapshot.prompt == "基础提示词\n\n背面要求"
    assert snapshot.image_count == 1
    assert snapshot.view_label == "背面"


@pytest.mark.asyncio
async def test_reference_images_are_stored_atomically(tmp_path: Path) -> None:
    database_path = tmp_path / "atomic-reference-images.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)
    history_id = await repository.create(
        user_id=1,
        kind="generate",
        prompt="原子写入",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=1,
    )
    batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)

    with pytest.raises(aiosqlite.IntegrityError):
        await repository.add_reference_images(
            user_id=1,
            history_id=history_id,
            batch_id=batch_id,
            images=[
                ("image/png", "first.png", b"first", "person"),
                ("image/png", "second.png", b"second", "invalid"),  # type: ignore[list-item]
            ],
        )

    detail = await repository.get(1, history_id)
    assert detail is not None
    assert detail.images == []


@pytest.mark.asyncio
async def test_history_repository_reports_missing_generation_batch_images(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "partial-generation.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)

    history_id = await repository.create(
        user_id=1,
        kind="generate",
        prompt="生成两张图片",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=2,
    )
    batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
    await repository.add_image(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
        role="generated",
        mime_type="image/png",
        filename="generated-1.png",
        position=0,
        data=b"only-one-image",
    )
    assert await repository.complete_generation_batch(history_id, batch_id, elapsed_ms=800)

    detail = await repository.get(1, history_id)
    batch = await repository.get_generation_batch(1, history_id, batch_id)

    assert detail is not None
    assert detail.status == "failed"
    assert detail.error_code == "partial_generation"
    assert len(detail.batches) == 1
    assert detail.batches[0].status == "failed"
    assert detail.batches[0].error_code == "partial_generation"
    assert detail.batches[0].image_count == 2
    assert detail.batches[0].generated_count == 1
    assert batch is not None
    assert batch.status == "failed"
    assert batch.image_count == 2
    assert batch.generated_count == 1
    assert len(batch.images) == 1


@pytest.mark.asyncio
async def test_deleting_one_generation_slot_does_not_stop_sibling_slots(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "deleted-generation-slot.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)
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

    assert await repository.delete_generation_slot(1, history_id, batch_id, 0)
    skipped = await repository.add_image(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
        role="generated",
        mime_type="image/png",
        filename="deleted.png",
        position=0,
        batch_position=0,
        data=b"deleted",
    )
    kept = await repository.add_image(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
        role="generated",
        mime_type="image/png",
        filename="kept.png",
        position=1,
        batch_position=1,
        data=b"kept",
    )
    assert skipped is None
    assert kept is not None
    assert await repository.complete_generation_batch(history_id, batch_id, elapsed_ms=100)

    batch = await repository.get_generation_batch(1, history_id, batch_id)
    assert batch is not None
    assert batch.status == "completed"
    assert batch.generated_count == 1
    assert batch.deleted_positions == [0]
    assert [image.batch_position for image in batch.images] == [1]

    assert await repository.delete_generated_image(1, history_id, kept)
    deleted_batch = await repository.get_generation_batch(1, history_id, batch_id)
    assert deleted_batch is not None
    assert deleted_batch.generated_count == 0
    assert deleted_batch.deleted_positions == [0, 1]
    assert deleted_batch.images == []


@pytest.mark.asyncio
async def test_cancelling_one_generation_slot_keeps_siblings_and_completes_batch(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cancelled-generation-slot.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)
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

    assert await repository.cancel_generation_slot(1, history_id, batch_id, 0)
    assert await repository.generation_slot_is_unavailable(1, history_id, batch_id, 0)
    skipped = await repository.add_image(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
        role="generated",
        mime_type="image/png",
        filename="cancelled.png",
        position=0,
        batch_position=0,
        data=b"cancelled",
    )
    kept = await repository.add_image(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
        role="generated",
        mime_type="image/png",
        filename="kept.png",
        position=1,
        batch_position=1,
        data=b"kept",
    )

    assert skipped is None
    assert kept is not None
    assert await repository.complete_generation_batch(history_id, batch_id, elapsed_ms=100)
    batch = await repository.get_generation_batch(1, history_id, batch_id)
    assert batch is not None
    assert batch.status == "completed"
    assert batch.cancelled_positions == [0]
    assert [image.batch_position for image in batch.images] == [1]

    assert await repository.delete_generation_slot(1, history_id, batch_id, 0)
    deleted_batch = await repository.get_generation_batch(1, history_id, batch_id)
    assert deleted_batch is not None
    assert deleted_batch.cancelled_positions == []
    assert deleted_batch.deleted_positions == [0]


@pytest.mark.asyncio
async def test_generation_tasks_keep_their_own_batch_snapshot(tmp_path: Path) -> None:
    database_path = tmp_path / "task-snapshots.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)

    history_id = await repository.create(
        user_id=1,
        project_id=1,
        kind="generate",
        prompt="第一批六张",
        provider="gemini",
        model="gemini-3.1-flash-image",
        detail="auto",
        image_count=6,
        size="1:1",
        resolution="1K",
    )
    first_batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
    first_task_id = await repository.create_generation_task(
        user_id=1,
        history_id=history_id,
        batch_id=first_batch_id,
    )
    assert await repository.cancel_generation_task(first_task_id, 1)
    second_batch_id = await repository.restart_generation(
        history_id,
        user_id=1,
        project_id=1,
        prompt="第二批两张",
        provider="grok",
        model="grok-imagine-image",
        detail="auto",
        image_count=2,
        size="16:9",
        resolution="2K",
    )
    second_task_id = await repository.create_generation_task(
        user_id=1,
        history_id=history_id,
        batch_id=second_batch_id,
    )

    tasks = {task["id"]: task for task in await repository.list_generation_tasks(1)}
    first = tasks[first_task_id]
    second = tasks[second_task_id]

    assert (first["batch_id"], first["prompt"], first["provider"], first["image_count"]) == (
        first_batch_id,
        "第一批六张",
        "gemini",
        6,
    )
    assert (second["batch_id"], second["prompt"], second["provider"], second["image_count"]) == (
        second_batch_id,
        "第二批两张",
        "grok",
        2,
    )
    assert first["project_id"] == second["project_id"] == 1


@pytest.mark.asyncio
async def test_pending_conversation_accepts_another_generation_batch(tmp_path: Path) -> None:
    database_path = tmp_path / "busy-conversation.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)

    history_id = await repository.create(
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
        history_id=history_id,
    )
    second_batch_id = await repository.restart_generation(
        history_id,
        user_id=1,
        project_id=1,
        prompt="并发续写",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=1,
    )

    detail = await repository.get(1, history_id)
    assert detail is not None
    assert detail.prompt == "并发续写"
    assert detail.status == "pending"
    assert len(detail.batches) == 2

    assert await repository.fail_generation_batch(
        history_id,
        second_batch_id,
        error_code="provider_request",
        error_message="第二批失败",
    )
    still_pending = await repository.get(1, history_id)
    assert still_pending is not None and still_pending.status == "pending"

    await repository.add_image(
        user_id=1,
        history_id=history_id,
        batch_id=first_batch_id,
        role="generated",
        mime_type="image/png",
        filename="first.png",
        position=0,
        batch_position=0,
        data=b"first",
    )
    assert await repository.complete_generation_batch(history_id, first_batch_id)
    completed = await repository.get(1, history_id)
    assert completed is not None
    assert completed.status == "failed"
    assert completed.error_message == "第二批失败"


@pytest.mark.asyncio
async def test_history_repository_records_failures_without_secrets(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)
    history_id = await repository.create(
        user_id=1,
        kind="analyze",
        prompt="描述图片",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=1,
    )

    await repository.fail(
        history_id,
        error_code="provider_auth",
        error_message="服务商鉴权失败",
    )
    detail = await repository.get(1, history_id)

    assert detail is not None
    assert detail.status == "failed"
    assert detail.error_code == "provider_auth"
    assert "key" not in (detail.error_message or "").lower()


@pytest.mark.asyncio
async def test_generation_task_has_independent_id_state_transitions_and_isolation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "generation-tasks.db"
    await initialize_database(database_path)
    users = UserRepository(database_path)
    await users.create("alice", hash_password("secret6"))
    await users.create("bob", hash_password("secret6"))
    repository = HistoryRepository(database_path)

    await repository.create(
        user_id=1,
        kind="generate",
        prompt="已有对话",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=1,
    )
    history_id = await repository.create(
        user_id=1,
        kind="generate",
        prompt="任务测试",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=1,
    )
    batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
    task_id = await repository.create_generation_task(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
    )

    assert task_id != history_id
    queued = await repository.get_generation_task(1, task_id)
    assert queued is not None
    assert queued["status"] == "queued"
    assert queued["batch_id"] == batch_id
    assert await repository.get_generation_task(2, task_id) is None
    listed = await repository.list_generation_tasks(1, active_only=True)
    assert [item["id"] for item in listed] == [task_id]

    assert await repository.mark_generation_task_running(task_id, 1, worker_id="worker-a")
    running = await repository.get_generation_task(1, task_id)
    assert running is not None
    assert running["status"] == "running"
    assert running["attempts"] == 1
    assert not await repository.mark_generation_task_running(
        task_id,
        1,
        worker_id="worker-b",
    )
    assert await repository.heartbeat_generation_task(
        task_id,
        1,
        worker_id="worker-a",
    )
    assert not await repository.heartbeat_generation_task(
        task_id,
        1,
        worker_id="worker-b",
    )

    assert not await repository.complete_generation_task(
        task_id,
        1,
        worker_id="worker-b",
    )
    assert await repository.complete_generation_task(
        task_id,
        1,
        worker_id="worker-a",
    )
    completed = await repository.get_generation_task(1, task_id)
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None


@pytest.mark.asyncio
async def test_only_stale_generation_leases_are_reaped(tmp_path: Path) -> None:
    database_path = tmp_path / "stale-generation.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)
    history_id = await repository.create(
        user_id=1,
        kind="generate",
        prompt="租约测试",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=1,
    )
    batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
    task_id = await repository.create_generation_task(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
    )
    assert await repository.mark_generation_task_running(task_id, 1, worker_id="worker-a")

    assert await repository.fail_stale_generation_tasks(stale_after_seconds=120) == 0
    active = await repository.get_generation_task(1, task_id)
    assert active is not None and active["status"] == "running"

    async with aiosqlite.connect(database_path) as connection:
        await connection.execute(
            "UPDATE generation_tasks SET heartbeat_at = datetime('now', '-5 minutes') WHERE id = ?",
            (task_id,),
        )
        await connection.commit()

    assert await repository.fail_stale_generation_tasks(stale_after_seconds=120) == 1
    stale = await repository.get_generation_task(1, task_id)
    batch = await repository.get_generation_batch(1, history_id, batch_id)
    detail = await repository.get(1, history_id)
    assert stale is not None and stale["status"] == "failed"
    assert batch is not None and batch.status == "failed"
    assert detail is not None and detail.status == "failed"


@pytest.mark.asyncio
async def test_queued_tasks_are_only_reaped_during_startup_recovery(tmp_path: Path) -> None:
    database_path = tmp_path / "queued-generation.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)
    history_id = await repository.create(
        user_id=1,
        kind="generate",
        prompt="等待并发槽位",
        provider="compatible",
        model="custom-model",
        detail="auto",
        image_count=1,
    )
    batch_id = await repository.latest_generation_batch_id(user_id=1, history_id=history_id)
    task_id = await repository.create_generation_task(
        user_id=1,
        history_id=history_id,
        batch_id=batch_id,
    )
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute(
            "UPDATE generation_tasks SET created_at = datetime('now', '-5 minutes') WHERE id = ?",
            (task_id,),
        )
        await connection.commit()

    assert await repository.fail_stale_generation_tasks(stale_after_seconds=120) == 0
    queued = await repository.get_generation_task(1, task_id)
    assert queued is not None and queued["status"] == "queued"

    assert await repository.fail_stale_generation_tasks(
        stale_after_seconds=120,
        include_queued=True,
    ) == 1
    interrupted = await repository.get_generation_task(1, task_id)
    batch = await repository.get_generation_batch(1, history_id, batch_id)
    detail = await repository.get(1, history_id)
    assert interrupted is not None and interrupted["status"] == "failed"
    assert batch is not None and batch.status == "failed"
    assert detail is not None and detail.status == "failed"


@pytest.mark.asyncio
async def test_cancelling_one_task_does_not_fail_another_conversation(tmp_path: Path) -> None:
    database_path = tmp_path / "cancel-one-task.db"
    await initialize_database(database_path)
    await UserRepository(database_path).create("alice", hash_password("secret6"))
    repository = HistoryRepository(database_path)

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

    assert await repository.cancel_generation_task(first_task_id, 1)
    first_task = await repository.get_generation_task(1, first_task_id)
    second_task = await repository.get_generation_task(1, second_task_id)
    first_batch = await repository.get_generation_batch(1, first_history_id, first_batch_id)
    second_batch = await repository.get_generation_batch(1, second_history_id, second_batch_id)
    first_detail = await repository.get(1, first_history_id)
    second_detail = await repository.get(1, second_history_id)

    assert first_task is not None and first_task["status"] == "cancelled"
    assert second_task is not None and second_task["status"] == "queued"
    assert first_batch is not None and first_batch.status == "failed"
    assert second_batch is not None and second_batch.status == "pending"
    assert first_detail is not None and first_detail.status == "failed"
    assert second_detail is not None and second_detail.status == "pending"

    assert await repository.cancel_generation_task(second_task_id, 1)
    second_detail = await repository.get(1, second_history_id)
    assert second_detail is not None and second_detail.status == "failed"
