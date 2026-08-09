from pathlib import Path

import aiosqlite
import pytest

from app.database import initialize_database
from app.repositories.api_key_config_repository import (
    ApiKeyConfigAliasTakenError,
    ApiKeyConfigRepository,
)
from app.repositories.user_repository import UserRepository


async def create_user(database_path: Path, username: str, api_key: str = "", model: str = "gpt-image-1.5") -> int:
    async with aiosqlite.connect(database_path) as connection:
        cursor = await connection.execute(
            "INSERT INTO users (username, password_hash, api_key, model) VALUES (?, 'hash', ?, ?)",
            (username, api_key, model),
        )
        await connection.commit()
    return int(cursor.lastrowid)


@pytest.mark.asyncio
async def test_migrates_existing_user_key_to_default_config(tmp_path: Path) -> None:
    database_path = tmp_path / "migration.db"
    await initialize_database(database_path)
    user_id = await create_user(database_path, "alice", "legacy-key", "gpt-image-1.5")

    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("PRAGMA user_version = 3")
        await connection.commit()

    await initialize_database(database_path)

    repository = ApiKeyConfigRepository(database_path)
    configs = await repository.list_for_user(user_id)
    async with aiosqlite.connect(database_path) as connection:
        active_id = (await (await connection.execute(
            "SELECT active_api_key_config_id FROM users WHERE id = ?", (user_id,)
        )).fetchone())[0]
    assert [(item.alias, item.provider_type, item.model, item.api_key) for item in configs] == [
        ("默认配置", "gpt", "gpt-image-1.5", "legacy-key")
    ]
    assert active_id == configs[0].id


@pytest.mark.asyncio
async def test_alias_is_unique_per_user_but_not_globally(tmp_path: Path) -> None:
    database_path = tmp_path / "repository.db"
    await initialize_database(database_path)
    first_user = await create_user(database_path, "alice")
    second_user = await create_user(database_path, "bob")
    repository = ApiKeyConfigRepository(database_path)

    first = await repository.create(first_user, "工作 Key", "key-a", "gpt", "gpt-image-2")
    second = await repository.create(second_user, "工作 Key", "key-b", "gemini", "gemini-3.1-flash-image")

    assert first.alias == second.alias
    with pytest.raises(ApiKeyConfigAliasTakenError):
        await repository.create(first_user, "工作 Key", "key-c", "gpt", "gpt-image-2")


@pytest.mark.asyncio
async def test_cannot_delete_last_config(tmp_path: Path) -> None:
    database_path = tmp_path / "delete.db"
    await initialize_database(database_path)
    user_id = await create_user(database_path, "alice")
    repository = ApiKeyConfigRepository(database_path)
    config = await repository.create(user_id, "唯一配置", "key", "gpt", "gpt-image-2")

    with pytest.raises(ValueError, match="last"):
        await repository.delete(user_id, config.id)


@pytest.mark.asyncio
async def test_new_user_receives_default_config(tmp_path: Path) -> None:
    database_path = tmp_path / "new-user.db"
    await initialize_database(database_path)
    user = await UserRepository(database_path).create("alice", "hash")

    configs = await ApiKeyConfigRepository(database_path).list_for_user(user.id)

    assert [(item.alias, item.provider_type, item.model) for item in configs] == [
        ("默认配置", "gpt", "gpt-image-1.5")
    ]
