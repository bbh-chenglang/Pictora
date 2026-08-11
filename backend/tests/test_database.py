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
    assert version == 7
    assert "api_key_configs" in tables
    assert "generation_batches" in tables
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
    assert version == 7


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
    assert version == 7


@pytest.mark.asyncio
async def test_database_migrates_version_six_history_images_into_batches(tmp_path: Path) -> None:
    database_path = tmp_path / "version-six.db"
    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        user_id = (await connection.execute(
            "INSERT INTO users (username, password_hash) VALUES ('alice', 'hash')"
        )).lastrowid
        project_id = (await (await connection.execute(
            "SELECT id FROM projects WHERE user_id = ?", (user_id,)
        )).fetchone())[0]
        history_id = (await connection.execute(
            """
            INSERT INTO history (
                user_id, project_id, kind, status, prompt, provider, model,
                detail, image_count, size, resolution
            )
            VALUES (?, ?, 'generate', 'completed', '旧提示词', 'gemini',
                    'gemini-image', 'high', 2, '16:9', '2K')
            """,
            (user_id, project_id),
        )).lastrowid
        await connection.execute("DROP INDEX IF EXISTS idx_history_images_batch_role_position")
        await connection.execute("ALTER TABLE history_images RENAME TO history_images_v7")
        await connection.execute(
            """
            CREATE TABLE history_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('reference', 'generated')),
                mime_type TEXT NOT NULL,
                filename TEXT,
                position INTEGER NOT NULL DEFAULT 0,
                data BLOB NOT NULL
            )
            """
        )
        await connection.execute(
            """
            INSERT INTO history_images (history_id, role, mime_type, filename, position, data)
            VALUES (?, 'reference', 'image/jpeg', 'person.jpg', 0, ?),
                   (?, 'generated', 'image/png', 'result.png', 0, ?)
            """,
            (history_id, b"reference", history_id, b"generated"),
        )
        await connection.execute("DROP TABLE history_images_v7")
        await connection.execute("DROP TABLE generation_batches")
        await connection.execute("PRAGMA user_version = 6")
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        batch = await (await connection.execute(
            """
            SELECT prompt, provider, model, detail, image_count, size, resolution
            FROM generation_batches WHERE history_id = ?
            """,
            (history_id,),
        )).fetchone()
        images = await (await connection.execute(
            """
            SELECT role, filename, batch_id, reference_category, data
            FROM history_images ORDER BY id
            """
        )).fetchall()
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]

    assert version == 7
    assert batch == ("旧提示词", "gemini", "gemini-image", "high", 2, "16:9", "2K")
    assert images[0][0:2] == ("reference", "person.jpg")
    assert images[0][2] is not None
    assert images[0][3] == "person"
    assert images[0][4] == b"reference"
    assert images[1][0:2] == ("generated", "result.png")
    assert images[1][2] == images[0][2]
    assert images[1][4] == b"generated"
