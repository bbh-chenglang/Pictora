from pathlib import Path

import aiosqlite

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "genimage.db"
FIXED_PROVIDER_NAME = "北海AI"
RELAY_BASE_URL = "https://sub.beibeihai.xyz"
OPENAI_BASE_URL = f"{RELAY_BASE_URL}/v1"
GEMINI_BASE_URL = f"{RELAY_BASE_URL}/v1beta"
# Kept for the legacy single-key settings API.
FIXED_BASE_URL = OPENAI_BASE_URL
SCHEMA_VERSION = 7

SCHEMA = f"""
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'gpt-image-1.5',
    active_api_key_config_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS api_key_configs (
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
CREATE TABLE IF NOT EXISTS user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, name)
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('generate', 'analyze')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 1,
    size TEXT,
    resolution TEXT,
    analysis_text TEXT,
    elapsed_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS generation_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
    api_key_config_id INTEGER REFERENCES api_key_configs(id) ON DELETE SET NULL,
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    image_count INTEGER NOT NULL,
    size TEXT,
    resolution TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS history_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
    batch_id INTEGER REFERENCES generation_batches(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('reference', 'generated')),
    reference_category TEXT CHECK (reference_category IN ('person', 'environment', 'object')),
    mime_type TEXT NOT NULL,
    filename TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_user_created_at ON history(user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_projects_user_updated ON projects(user_id, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_history_project_created_at ON history(project_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_history_images_history_id ON history_images(history_id, position);
CREATE INDEX IF NOT EXISTS idx_history_images_batch_role_position ON history_images(batch_id, role, position);
CREATE TRIGGER IF NOT EXISTS trg_users_default_project
AFTER INSERT ON users
BEGIN
    INSERT INTO projects (user_id, name) VALUES (NEW.id, '第一个项目');
END;
"""


async def _remove_empty_default_api_key_configs(connection: aiosqlite.Connection) -> None:
    tables = {
        row[0]
        for row in await (await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )).fetchall()
    }
    if not {"users", "api_key_configs"}.issubset(tables):
        return
    await connection.execute(
        """
        DELETE FROM api_key_configs
        WHERE alias = '默认配置'
          AND provider_type = 'gpt'
          AND trim(api_key) = ''
        """
    )
    await connection.execute(
        """
        UPDATE users
        SET active_api_key_config_id = (
            SELECT id
            FROM api_key_configs
            WHERE api_key_configs.user_id = users.id
            ORDER BY created_at ASC, id ASC
            LIMIT 1
        )
        WHERE active_api_key_config_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM api_key_configs
              WHERE api_key_configs.id = users.active_api_key_config_id
                AND api_key_configs.user_id = users.id
          )
        """
    )


async def _migrate_generation_batches(connection: aiosqlite.Connection) -> None:
    tables = {
        row[0]
        for row in await (await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )).fetchall()
    }
    if not {"history", "history_images"}.issubset(tables):
        return

    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
            api_key_config_id INTEGER REFERENCES api_key_configs(id) ON DELETE SET NULL,
            prompt TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            detail TEXT NOT NULL,
            image_count INTEGER NOT NULL,
            size TEXT,
            resolution TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    image_columns = {
        row[1]
        for row in await (await connection.execute("PRAGMA table_info(history_images)")).fetchall()
    }
    if "batch_id" not in image_columns:
        await connection.execute(
            "ALTER TABLE history_images ADD COLUMN batch_id INTEGER REFERENCES generation_batches(id) ON DELETE CASCADE"
        )
    if "reference_category" not in image_columns:
        await connection.execute(
            """
            ALTER TABLE history_images
            ADD COLUMN reference_category TEXT
            CHECK (reference_category IN ('person', 'environment', 'object'))
            """
        )
    history_columns = {
        row[1]
        for row in await (await connection.execute("PRAGMA table_info(history)")).fetchall()
    }
    required_history_columns = {
        "id", "prompt", "provider", "model", "detail", "image_count", "size", "resolution"
    }
    if required_history_columns.issubset(history_columns):
        await connection.execute(
            """
            INSERT INTO generation_batches (
                history_id, prompt, provider, model, detail, image_count, size, resolution, created_at
            )
            SELECT history.id, history.prompt, history.provider, history.model, history.detail,
                   history.image_count, history.size, history.resolution, history.created_at
            FROM history
            WHERE NOT EXISTS (
                SELECT 1 FROM generation_batches WHERE generation_batches.history_id = history.id
            )
            """
        )
        await connection.execute(
            """
            UPDATE history_images
            SET batch_id = (
                SELECT generation_batches.id
                FROM generation_batches
                WHERE generation_batches.history_id = history_images.history_id
                ORDER BY generation_batches.id DESC
                LIMIT 1
            )
            WHERE batch_id IS NULL
            """
        )
    await connection.execute(
        """
        UPDATE history_images
        SET reference_category = 'person'
        WHERE role = 'reference' AND reference_category IS NULL
        """
    )
    await connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_history_images_batch_role_position
        ON history_images(batch_id, role, position)
        """
    )


async def initialize_database(path: Path = DATABASE_PATH, **_: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as connection:
        await connection.execute("PRAGMA foreign_keys = ON")
        cursor = await connection.execute("PRAGMA user_version")
        version = (await cursor.fetchone())[0]
        if version < 2:
            await connection.execute("DROP TABLE IF EXISTS history_images")
            await connection.execute("DROP TABLE IF EXISTS history")
            await connection.execute("DROP TABLE IF EXISTS settings")
            await connection.executescript(SCHEMA)
        elif version < 3:
            await connection.execute("BEGIN")
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, name)
                )
                """
            )
            await connection.execute(
                """
                INSERT INTO projects (user_id, name)
                SELECT id, '第一个项目' FROM users
                WHERE NOT EXISTS (
                    SELECT 1 FROM projects WHERE projects.user_id = users.id
                )
                """
            )
            await connection.execute("ALTER TABLE history_images RENAME TO history_images_old")
            await connection.execute("ALTER TABLE history RENAME TO history_old")
            await connection.execute(
                """
                CREATE TABLE history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL CHECK (kind IN ('generate', 'analyze')),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
                    prompt TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    image_count INTEGER NOT NULL DEFAULT 1,
                    size TEXT,
                    resolution TEXT,
                    analysis_text TEXT,
                    elapsed_ms INTEGER,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
                """
            )
            await connection.execute(
                """
                INSERT INTO history (
                    id, user_id, project_id, kind, status, prompt, provider, model,
                    detail, image_count, size, resolution, analysis_text, elapsed_ms, error_code,
                    error_message, created_at, completed_at
                )
                SELECT h.id, h.user_id, p.id, h.kind, h.status, h.prompt, h.provider,
                       h.model, h.detail, h.image_count, h.size, NULL, h.analysis_text,
                       h.elapsed_ms, h.error_code, h.error_message, h.created_at,
                       h.completed_at
                FROM history_old AS h
                JOIN projects AS p ON p.user_id = h.user_id
                """
            )
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
                INSERT INTO history_images (id, history_id, role, mime_type, filename, position, data)
                SELECT image.id, image.history_id, image.role, image.mime_type,
                       image.filename, image.position, image.data
                FROM history_images_old AS image
                JOIN history AS h ON h.id = image.history_id
                """
            )
            await connection.execute("DROP TABLE history_images_old")
            await connection.execute("DROP TABLE history_old")
            await connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_history_user_created_at ON history(user_id, created_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_projects_user_updated ON projects(user_id, updated_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_history_project_created_at ON history(project_id, created_at DESC, id DESC);
                CREATE INDEX IF NOT EXISTS idx_history_images_history_id ON history_images(history_id, position);
                CREATE TRIGGER IF NOT EXISTS trg_users_default_project
                AFTER INSERT ON users
                BEGIN
                    INSERT INTO projects (user_id, name) VALUES (NEW.id, '第一个项目');
                END;
                """
            )
            await _migrate_generation_batches(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 4:
            await connection.execute("BEGIN")
            user_columns = {
                row[1]
                for row in await (await connection.execute("PRAGMA table_info(users)")).fetchall()
            }
            if "active_api_key_config_id" not in user_columns:
                await connection.execute(
                    "ALTER TABLE users ADD COLUMN active_api_key_config_id INTEGER"
                )
            history_columns = {
                row[1]
                for row in await (await connection.execute("PRAGMA table_info(history)")).fetchall()
            }
            if "resolution" not in history_columns:
                await connection.execute("ALTER TABLE history ADD COLUMN resolution TEXT")
            await connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_key_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    alias TEXT NOT NULL,
                    api_key TEXT NOT NULL DEFAULT '',
                    provider_type TEXT NOT NULL CHECK (provider_type IN ('gpt', 'gemini')),
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (user_id, alias)
                )
                """
            )
            users = await (await connection.execute(
                "SELECT id, api_key, model FROM users"
            )).fetchall()
            for user_id, api_key, model in users:
                active = await (await connection.execute(
                    "SELECT id FROM api_key_configs WHERE user_id = ? ORDER BY id LIMIT 1",
                    (user_id,),
                )).fetchone()
                if active is None and str(api_key or "").strip():
                    cursor = await connection.execute(
                        """
                        INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
                        VALUES (?, '默认配置', ?, 'gpt', ?)
                        """,
                        (user_id, api_key, model),
                    )
                    active_id = cursor.lastrowid
                else:
                    active_id = active[0] if active else None
                await connection.execute(
                    "UPDATE users SET active_api_key_config_id = ? WHERE id = ?",
                    (active_id, user_id),
                )
            await _remove_empty_default_api_key_configs(connection)
            await _migrate_generation_batches(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 5:
            await connection.execute("BEGIN")
            history_columns = {
                row[1]
                for row in await (await connection.execute("PRAGMA table_info(history)")).fetchall()
            }
            if "resolution" not in history_columns:
                await connection.execute("ALTER TABLE history ADD COLUMN resolution TEXT")
            await _remove_empty_default_api_key_configs(connection)
            await _migrate_generation_batches(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 6:
            await connection.execute("BEGIN")
            await _remove_empty_default_api_key_configs(connection)
            await _migrate_generation_batches(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 7:
            await connection.execute("BEGIN")
            await _migrate_generation_batches(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        else:
            await connection.executescript(SCHEMA)
            await _migrate_generation_batches(connection)
        await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await connection.commit()
