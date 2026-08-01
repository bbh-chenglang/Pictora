from pathlib import Path

import pytest

from app.auth import hash_password
from app.database import initialize_database
from app.repositories.history_repository import HistoryRepository
from app.repositories.user_repository import UserRepository


@pytest.mark.asyncio
async def test_history_repository_keeps_records_and_images_with_their_owner(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "personal-data.db"
    await initialize_database(database_path)
    users = UserRepository(database_path)
    alice = await users.create("alice", hash_password("secret6"))
    bob = await users.create("bob", hash_password("secret6"))
    history = HistoryRepository(database_path)

    alice_history = await history.create(
        user_id=alice.id,
        kind="generate",
        prompt="alice image",
        provider="compatible",
        model="gpt-image-1.5",
        detail="high",
        image_count=1,
    )
    bob_history = await history.create(
        user_id=bob.id,
        kind="generate",
        prompt="bob image",
        provider="compatible",
        model="gpt-image-1.5",
        detail="high",
        image_count=1,
    )
    image_id = await history.add_image(
        user_id=bob.id,
        history_id=bob_history,
        role="generated",
        mime_type="image/png",
        filename="bob.png",
        position=0,
        data=b"bob-image",
    )

    assert [item.id for item in await history.list(user_id=alice.id)] == [alice_history]
    assert await history.get(alice.id, bob_history) is None
    assert await history.get_image(alice.id, bob_history, image_id) is None
