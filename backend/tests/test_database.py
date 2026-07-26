from pathlib import Path

import aiosqlite
import pytest

from app.database import FIXED_BASE_URL, FIXED_PROVIDER_NAME, initialize_database
from app.repositories.settings_repository import SettingsRepository


@pytest.mark.asyncio
async def test_database_seeds_fixed_provider_settings(tmp_path: Path) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(
        database_path,
        default_model="gpt-image-1.5",
        default_api_key="",
    )

    settings = await SettingsRepository(database_path).get()

    assert settings.provider_name == FIXED_PROVIDER_NAME
    assert settings.base_url == FIXED_BASE_URL
    assert settings.model == "gpt-image-1.5"
    assert settings.api_key == ""


@pytest.mark.asyncio
async def test_settings_update_persists_only_model_and_api_key(tmp_path: Path) -> None:
    database_path = tmp_path / "genimage.db"
    await initialize_database(
        database_path,
        default_model="old-model",
        default_api_key="old-key",
    )
    repository = SettingsRepository(database_path)

    updated = await repository.update(model="new-model", api_key="new-key")
    reloaded = await SettingsRepository(database_path).get()

    assert updated == reloaded
    assert reloaded.model == "new-model"
    assert reloaded.api_key == "new-key"
    assert reloaded.base_url == FIXED_BASE_URL


@pytest.mark.asyncio
async def test_database_migrates_existing_history_with_size_column(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute(
            """
            CREATE TABLE history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                prompt TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                detail TEXT NOT NULL,
                image_count INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        cursor = await connection.execute("PRAGMA table_info(history)")
        columns = {row[1] for row in await cursor.fetchall()}
    assert "size" in columns
