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
    assert version == 6
    assert "api_key_configs" in tables
    async with aiosqlite.connect(database_path) as connection:
        columns = {
            row[1]
            for row in await (await connection.execute("PRAGMA table_info(history)")).fetchall()
        }
    assert "project_id" in columns
    assert "resolution" in columns

    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("INSERT INTO users (username, password_hash) VALUES ('alice', 'hash')")
        await connection.commit()
    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        user_count = (await (await connection.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
    assert user_count == 1


@pytest.mark.asyncio
async def test_database_adds_resolution_to_version_four_history(tmp_path: Path) -> None:
    database_path = tmp_path / "version-four.db"
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute(
            "CREATE TABLE history (id INTEGER PRIMARY KEY, size TEXT)"
        )
        await connection.execute("PRAGMA user_version = 4")
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        columns = {
            row[1]
            for row in await (await connection.execute("PRAGMA table_info(history)")).fetchall()
        }
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]
    assert "resolution" in columns
    assert version == 6


@pytest.mark.asyncio
async def test_database_removes_only_empty_generated_default_configs(tmp_path: Path) -> None:
    database_path = tmp_path / "version-five.db"
    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        first_user = (await connection.execute(
            "INSERT INTO users (username, password_hash) VALUES ('alice', 'hash')"
        )).lastrowid
        second_user = (await connection.execute(
            "INSERT INTO users (username, password_hash) VALUES ('bob', 'hash')"
        )).lastrowid
        generated = (await connection.execute(
            """
            INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
            VALUES (?, '默认配置', '', 'gpt', 'gpt-image-1.5')
            """,
            (first_user,),
        )).lastrowid
        replacement = (await connection.execute(
            """
            INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
            VALUES (?, 'Gemini', '', 'gemini', 'gemini-3.1-flash-image')
            """,
            (first_user,),
        )).lastrowid
        preserved = (await connection.execute(
            """
            INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
            VALUES (?, '默认配置', 'real-key', 'gpt', 'gpt-image-1.5')
            """,
            (second_user,),
        )).lastrowid
        await connection.execute(
            "UPDATE users SET active_api_key_config_id = ? WHERE id = ?",
            (generated, first_user),
        )
        await connection.execute("PRAGMA user_version = 5")
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        configs = await (await connection.execute(
            "SELECT id, alias, api_key, provider_type FROM api_key_configs ORDER BY id"
        )).fetchall()
        active_id = (await (await connection.execute(
            "SELECT active_api_key_config_id FROM users WHERE id = ?", (first_user,)
        )).fetchone())[0]
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]
    assert configs == [
        (replacement, "Gemini", "", "gemini"),
        (preserved, "默认配置", "real-key", "gpt"),
    ]
    assert active_id == replacement
    assert version == 6
