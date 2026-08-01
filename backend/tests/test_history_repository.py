from pathlib import Path

import pytest

from app.database import initialize_database
from app.auth import hash_password
from app.repositories.history_repository import HistoryRepository
from app.repositories.user_repository import UserRepository


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
    assert detail.images[0].role == "generated"
    assert (
        detail.images[0].url
        == f"/api/history/{history_id}/images/{detail.images[0].id}"
    )
    assert image is not None
    assert image.data == b"png-bytes"


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
