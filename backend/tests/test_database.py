from pathlib import Path

import aiosqlite
import pytest

from app.database import initialize_database


@pytest.mark.asyncio
async def test_database_removes_legacy_global_data_once(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(database_path) as connection:
        await connection.executescript(
            """
            CREATE TABLE settings (id INTEGER PRIMARY KEY, api_key TEXT NOT NULL);
            CREATE TABLE history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
        await connection.execute(
            "CREATE TABLE history_images (id INTEGER PRIMARY KEY, history_id INTEGER, data BLOB)"
        )
        await connection.execute("INSERT INTO settings (id, api_key) VALUES (1, 'legacy-key')")
        await connection.execute("INSERT INTO history (kind, status, prompt, provider, model, detail) VALUES ('generate', 'completed', 'legacy', 'p', 'm', 'd')")
        await connection.execute("PRAGMA user_version = 1")
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        cursor = await connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tables = {row[0] for row in await cursor.fetchall()}
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]
        history_count = (await (await connection.execute("SELECT COUNT(*) FROM history")).fetchone())[0]
    assert {"users", "user_sessions", "history", "history_images"}.issubset(tables)
    assert "settings" not in tables
    assert history_count == 0
    assert version == 3
    async with aiosqlite.connect(database_path) as connection:
        columns = {
            row[1]
            for row in await (await connection.execute("PRAGMA table_info(history)")).fetchall()
        }
    assert "project_id" in columns

    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("INSERT INTO users (username, password_hash) VALUES ('alice', 'hash')")
        await connection.commit()
    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        user_count = (await (await connection.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
    assert user_count == 1
