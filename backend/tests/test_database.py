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
    assert {
        "users",
        "user_sessions",
        "history",
        "history_images",
        "history_image_thumbnails",
    }.issubset(tables)
    assert "settings" not in tables
    assert history_count == 0
    assert version == 17
    assert "api_key_configs" in tables
    assert "generation_batches" in tables
    assert "email_verification_codes" in tables
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
    assert version == 17


@pytest.mark.asyncio
async def test_database_migrates_fixed_prompt_categories_to_free_text(tmp_path: Path) -> None:
    database_path = tmp_path / "prompt-category-migration.db"
    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("DROP INDEX IF EXISTS idx_prompt_entries_user_updated")
        await connection.execute("DROP INDEX IF EXISTS idx_prompt_entries_user_category")
        await connection.execute("DROP TABLE prompt_entries")
        user_id = (await connection.execute(
            "INSERT INTO users (username, password_hash) VALUES ('alice', 'hash')"
        )).lastrowid
        await connection.execute(
            """
            CREATE TABLE prompt_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                category TEXT NOT NULL CHECK (category IN ('portrait', 'product', 'marketing', 'illustration', 'other')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await connection.execute(
            "INSERT INTO prompt_entries (user_id, name, prompt, category) VALUES (?, '旧提示词', '旧内容', 'portrait')",
            (user_id,),
        )
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        row = await (await connection.execute(
            "SELECT category FROM prompt_entries WHERE name = '旧提示词'"
        )).fetchone()
        schema = await (await connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'prompt_entries'"
        )).fetchone()
    assert row[0] == "portrait"
    assert "CHECK" not in schema[0].upper()


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
    assert version == 17


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

    assert version == 17
    assert batch == ("旧提示词", "gemini", "gemini-image", "high", 2, "16:9", "2K")
    assert images[0][0:2] == ("reference", "person.jpg")
    assert images[0][2] is not None
    assert images[0][3] == "person"
    assert images[0][4] == b"reference"
    assert images[1][0:2] == ("generated", "result.png")
    assert images[1][2] == images[0][2]
    assert images[1][4] == b"generated"


@pytest.mark.asyncio
async def test_database_adds_grok_without_losing_existing_config_links(tmp_path: Path) -> None:
    database_path = tmp_path / "version-eight.db"
    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        user_id = (await connection.execute(
            "INSERT INTO users (username, password_hash) VALUES ('alice', 'hash')"
        )).lastrowid
        config_id = (await connection.execute(
            """
            INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
            VALUES (?, 'OpenAI', 'secret', 'gpt', 'gpt-image-2')
            """,
            (user_id,),
        )).lastrowid
        project_id = (await (await connection.execute(
            "SELECT id FROM projects WHERE user_id = ?", (user_id,)
        )).fetchone())[0]
        history_id = (await connection.execute(
            """
            INSERT INTO history (
                user_id, project_id, kind, status, prompt, provider, model, detail
            ) VALUES (?, ?, 'generate', 'completed', 'draw', 'compatible',
                      'gpt-image-2', 'high')
            """,
            (user_id, project_id),
        )).lastrowid
        batch_id = (await connection.execute(
            """
            INSERT INTO generation_batches (
                history_id, api_key_config_id, prompt, provider, model, detail, image_count
            ) VALUES (?, ?, 'draw', 'compatible', 'gpt-image-2', 'high', 1)
            """,
            (history_id, config_id),
        )).lastrowid
        await connection.execute(
            "UPDATE users SET active_api_key_config_id = ? WHERE id = ?",
            (config_id, user_id),
        )
        await connection.commit()
        await connection.execute("PRAGMA foreign_keys = OFF")
        await connection.executescript(
            """
            CREATE TABLE api_key_configs_v8 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                alias TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                provider_type TEXT NOT NULL CHECK (provider_type IN ('gpt', 'gemini')),
                model TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, alias)
            );
            INSERT INTO api_key_configs_v8 SELECT * FROM api_key_configs;
            DROP TABLE api_key_configs;
            ALTER TABLE api_key_configs_v8 RENAME TO api_key_configs;
            PRAGMA user_version = 8;
            """
        )
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        config = await (await connection.execute(
            "SELECT id, provider_type, model FROM api_key_configs WHERE id = ?",
            (config_id,),
        )).fetchone()
        linked_config_id = (await (await connection.execute(
            "SELECT api_key_config_id FROM generation_batches WHERE id = ?", (batch_id,)
        )).fetchone())[0]
        active_config_id = (await (await connection.execute(
            "SELECT active_api_key_config_id FROM users WHERE id = ?", (user_id,)
        )).fetchone())[0]
        await connection.execute(
            """
            INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
            VALUES (?, 'Grok', 'secret', 'grok', 'grok-imagine-image')
            """,
            (user_id,),
        )
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]

    assert config == (config_id, "gpt", "gpt-image-2")
    assert linked_config_id == config_id
    assert active_config_id == config_id
    assert version == 17


@pytest.mark.asyncio
async def test_database_adds_native_image_parameters_to_version_nine_batches(tmp_path: Path) -> None:
    database_path = tmp_path / "version-nine.db"
    async with aiosqlite.connect(database_path) as connection:
        await connection.executescript(
            """
            CREATE TABLE history (
                id INTEGER PRIMARY KEY,
                prompt TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                detail TEXT NOT NULL,
                image_count INTEGER NOT NULL,
                size TEXT,
                resolution TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE generation_batches (
                id INTEGER PRIMARY KEY,
                history_id INTEGER NOT NULL,
                prompt TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                detail TEXT NOT NULL,
                image_count INTEGER NOT NULL,
                size TEXT,
                resolution TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE history_images (
                id INTEGER PRIMARY KEY,
                history_id INTEGER NOT NULL,
                batch_id INTEGER,
                role TEXT NOT NULL,
                reference_category TEXT,
                position INTEGER NOT NULL DEFAULT 0
            );
            PRAGMA user_version = 9;
            """
        )
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        columns = {
            row[1]
            for row in await (await connection.execute(
                "PRAGMA table_info(generation_batches)"
            )).fetchall()
        }
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]

        assert {
            "output_format", "background", "output_compression", "moderation",
            "status", "elapsed_ms", "error_code", "error_message", "completed_at",
            "views_json",
        }.issubset(columns)
    assert version == 17


@pytest.mark.asyncio
async def test_database_migrates_version_twelve_generation_task_leases(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "version-twelve.db"
    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("ALTER TABLE generation_tasks DROP COLUMN worker_id")
        await connection.execute("ALTER TABLE generation_tasks DROP COLUMN heartbeat_at")
        await connection.execute("PRAGMA user_version = 12")
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        columns = {
            row[1]
            for row in await (await connection.execute(
                "PRAGMA table_info(generation_tasks)"
            )).fetchall()
        }
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]

    assert {"worker_id", "heartbeat_at"}.issubset(columns)
    assert version == 17


@pytest.mark.asyncio
async def test_database_migrates_generation_slot_deletions_from_version_thirteen(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "version-thirteen.db"
    await initialize_database(database_path)
    async with aiosqlite.connect(database_path) as connection:
        await connection.execute("DROP TABLE generation_batch_deleted_slots")
        await connection.execute("DROP TABLE generation_batch_cancelled_slots")
        await connection.execute("ALTER TABLE history_images DROP COLUMN batch_position")
        await connection.execute("PRAGMA user_version = 13")
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        image_columns = {
            row[1]
            for row in await (await connection.execute(
                "PRAGMA table_info(history_images)"
            )).fetchall()
        }
        slot_table = await (await connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'generation_batch_deleted_slots'"
        )).fetchone()
        cancelled_slot_table = await (await connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'generation_batch_cancelled_slots'"
        )).fetchone()
        version = (await (await connection.execute("PRAGMA user_version")).fetchone())[0]

    assert "batch_position" in image_columns
    assert slot_table is not None
    assert cancelled_slot_table is not None
    assert version == 17


@pytest.mark.asyncio
async def test_database_backfills_completed_partial_generation_statuses(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "partial-generation.db"
    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        user_cursor = await connection.execute(
            "INSERT INTO users (username, password_hash) VALUES ('partial-user', 'hash')"
        )
        user_id = int(user_cursor.lastrowid)
        project_id = int((await (await connection.execute(
            "SELECT id FROM projects WHERE user_id = ?", (user_id,)
        )).fetchone())[0])
        history_cursor = await connection.execute(
            """
            INSERT INTO history (
                user_id, project_id, kind, status, prompt, provider, model,
                detail, image_count, error_code, error_message
            ) VALUES (?, ?, 'generate', 'completed', 'prompt', 'openai', 'model',
                      'auto', 3, NULL, NULL)
            """,
            (user_id, project_id),
        )
        history_id = int(history_cursor.lastrowid)
        task_cursor = await connection.execute(
            """
            INSERT INTO generation_tasks (user_id, history_id, status)
            VALUES (?, ?, 'completed')
            """,
            (user_id, history_id),
        )
        task_id = int(task_cursor.lastrowid)
        await connection.execute(
            """
            INSERT INTO generation_batches (
                history_id, task_id, prompt, provider, model, detail,
                image_count, generated_count, status
            ) VALUES (?, ?, 'prompt', 'openai', 'model', 'auto', 3, 2, 'completed')
            """,
            (history_id, task_id),
        )
        await connection.commit()

    await initialize_database(database_path)

    async with aiosqlite.connect(database_path) as connection:
        batch = await (await connection.execute(
            "SELECT status, error_code FROM generation_batches WHERE task_id = ?",
            (task_id,),
        )).fetchone()
        task = await (await connection.execute(
            "SELECT status, error_code FROM generation_tasks WHERE id = ?", (task_id,)
        )).fetchone()
        history = await (await connection.execute(
            "SELECT status, error_code FROM history WHERE id = ?", (history_id,)
        )).fetchone()

    assert batch == ("failed", "partial_generation")
    assert task == ("failed", "partial_generation")
    assert history == ("failed", "partial_generation")
