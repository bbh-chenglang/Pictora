from pathlib import Path

import aiosqlite

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "genimage.db"
FIXED_PROVIDER_NAME = "北海AI"
RELAY_BASE_URL = "https://sub.beibeihai.xyz"
OPENAI_BASE_URL = f"{RELAY_BASE_URL}/v1"
GEMINI_BASE_URL = f"{RELAY_BASE_URL}/v1beta"
# Kept for the legacy single-key settings API.
FIXED_BASE_URL = OPENAI_BASE_URL
SCHEMA_VERSION = 17

SCHEMA = f"""
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    email TEXT,
    email_verified_at TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1)),
    password_hash TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'gpt-image-1.5',
    active_api_key_config_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT,
    last_activity_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
ON users(lower(email)) WHERE email IS NOT NULL;
CREATE TABLE IF NOT EXISTS email_verification_codes (
    email TEXT PRIMARY KEY COLLATE NOCASE,
    code_hash TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_sent_at TEXT NOT NULL,
    failed_attempts INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS api_key_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    provider_type TEXT NOT NULL CHECK (provider_type IN ('gpt', 'gemini', 'grok')),
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
    task_id INTEGER REFERENCES generation_tasks(id) ON DELETE SET NULL,
    history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
    api_key_config_id INTEGER REFERENCES api_key_configs(id) ON DELETE SET NULL,
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    image_count INTEGER NOT NULL,
    generated_count INTEGER,
    size TEXT,
    resolution TEXT,
    output_format TEXT,
    background TEXT,
    output_compression INTEGER,
    moderation TEXT,
    views_json TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
    elapsed_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS generation_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0,
    worker_id TEXT,
    heartbeat_at TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT
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
    batch_position INTEGER,
    data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS history_image_thumbnails (
    image_id INTEGER PRIMARY KEY REFERENCES history_images(id) ON DELETE CASCADE,
    mime_type TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    data BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS generation_batch_deleted_slots (
    batch_id INTEGER NOT NULL REFERENCES generation_batches(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, position)
);
CREATE TABLE IF NOT EXISTS generation_batch_cancelled_slots (
    batch_id INTEGER NOT NULL REFERENCES generation_batches(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, position)
);
CREATE TABLE IF NOT EXISTS skills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('portrait', 'product', 'marketing', 'illustration', 'other')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'pending', 'published', 'rejected')),
    workflow_json TEXT NOT NULL,
    cover_mime_type TEXT,
    cover_data BLOB,
    moderation_note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TEXT
);
CREATE TABLE IF NOT EXISTS skill_favorites (
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (skill_id, user_id)
);
CREATE TABLE IF NOT EXISTS skill_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS prompt_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_history_user_created_at ON history(user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_projects_user_updated ON projects(user_id, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_history_project_created_at ON history(project_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_history_images_history_id ON history_images(history_id, position);
CREATE INDEX IF NOT EXISTS idx_history_images_batch_role_position ON history_images(batch_id, role, position);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_user_created ON generation_tasks(user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_generation_tasks_history ON generation_tasks(history_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_deleted_slots_batch ON generation_batch_deleted_slots(batch_id, position);
CREATE INDEX IF NOT EXISTS idx_cancelled_slots_batch ON generation_batch_cancelled_slots(batch_id, position);
CREATE INDEX IF NOT EXISTS idx_skills_status_updated ON skills(status, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_skills_user_updated ON skills(user_id, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_skill_uses_skill ON skill_uses(skill_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_prompt_entries_user_updated ON prompt_entries(user_id, updated_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_prompt_entries_user_category ON prompt_entries(user_id, category);
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
            generated_count INTEGER,
            size TEXT,
            resolution TEXT,
            output_format TEXT,
            background TEXT,
            output_compression INTEGER,
            moderation TEXT,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
            elapsed_ms INTEGER,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        )
        """
    )


async def _migrate_history_image_thumbnails(connection: aiosqlite.Connection) -> None:
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS history_image_thumbnails (
            image_id INTEGER PRIMARY KEY REFERENCES history_images(id) ON DELETE CASCADE,
            mime_type TEXT NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            data BLOB NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


async def _migrate_generation_tasks(connection: aiosqlite.Connection) -> None:
    await _migrate_history_image_thumbnails(connection)
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
            attempts INTEGER NOT NULL DEFAULT 0,
            worker_id TEXT,
            heartbeat_at TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            completed_at TEXT
        )
        """
    )
    tables = {
        row[0]
        for row in await (await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )).fetchall()
    }
    if "generation_batches" not in tables:
        return
    columns = {
        row[1]
        for row in await (await connection.execute("PRAGMA table_info(generation_batches)" )).fetchall()
    }
    task_columns = {
        row[1]
        for row in await (await connection.execute("PRAGMA table_info(generation_tasks)" )).fetchall()
    }
    for name, declaration in {
        "worker_id": "TEXT",
        "heartbeat_at": "TEXT",
    }.items():
        if name not in task_columns:
            await connection.execute(
                f"ALTER TABLE generation_tasks ADD COLUMN {name} {declaration}"
            )
    if "task_id" not in columns:
        await connection.execute(
            "ALTER TABLE generation_batches ADD COLUMN task_id INTEGER REFERENCES generation_tasks(id) ON DELETE SET NULL"
        )
    await connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_generation_tasks_user_created ON generation_tasks(user_id, created_at DESC, id DESC)"
    )
    await connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_generation_tasks_history ON generation_tasks(history_id, id DESC)"
    )
    batch_columns = {
        row[1]
        for row in await (await connection.execute("PRAGMA table_info(generation_batches)")).fetchall()
    }
    for name, declaration in {
        "output_format": "TEXT",
        "background": "TEXT",
        "output_compression": "INTEGER",
        "moderation": "TEXT",
        "status": "TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed'))",
        "elapsed_ms": "INTEGER",
        "error_code": "TEXT",
        "error_message": "TEXT",
        "completed_at": "TEXT",
        "generated_count": "INTEGER",
        "views_json": "TEXT",
    }.items():
        if name not in batch_columns:
            await connection.execute(
                f"ALTER TABLE generation_batches ADD COLUMN {name} {declaration}"
            )
    if "history_images" in tables:
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
        if "batch_position" not in image_columns:
            await connection.execute(
                "ALTER TABLE history_images ADD COLUMN batch_position INTEGER"
            )
            await connection.execute(
                """
                UPDATE history_images AS image
                SET batch_position = (
                    SELECT COUNT(*)
                    FROM history_images AS earlier
                    WHERE earlier.batch_id = image.batch_id
                      AND earlier.role = 'generated'
                      AND (
                          earlier.position < image.position
                          OR (earlier.position = image.position AND earlier.id < image.id)
                      )
                )
                WHERE image.role = 'generated' AND image.batch_id IS NOT NULL
                """
            )
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_batch_deleted_slots (
            batch_id INTEGER NOT NULL REFERENCES generation_batches(id) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (batch_id, position)
        )
        """
    )
    await connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_slots_batch ON generation_batch_deleted_slots(batch_id, position)"
    )
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS generation_batch_cancelled_slots (
            batch_id INTEGER NOT NULL REFERENCES generation_batches(id) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position >= 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (batch_id, position)
        )
        """
    )
    await connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_cancelled_slots_batch ON generation_batch_cancelled_slots(batch_id, position)"
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
        if "history_images" in tables:
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
        if "status" in history_columns:
            await connection.execute(
                """
                UPDATE generation_batches
                SET status = CASE
                    WHEN id = (
                        SELECT latest.id FROM generation_batches AS latest
                        WHERE latest.history_id = generation_batches.history_id
                        ORDER BY latest.id DESC LIMIT 1
                    ) THEN COALESCE((
                        SELECT history.status FROM history
                        WHERE history.id = generation_batches.history_id
                    ), 'completed')
                    ELSE 'completed'
                END
                WHERE status = 'pending'
                  AND NOT (
                      id = (
                          SELECT latest.id FROM generation_batches AS latest
                          WHERE latest.history_id = generation_batches.history_id
                          ORDER BY latest.id DESC LIMIT 1
                      )
                      AND EXISTS (
                          SELECT 1 FROM history
                          WHERE history.id = generation_batches.history_id
                            AND history.status = 'pending'
                      )
                  )
                """
            )
        else:
            await connection.execute(
                "UPDATE generation_batches SET status = 'completed' WHERE status = 'pending'"
            )
    await connection.execute(
        """
        UPDATE generation_batches
        SET generated_count = (
            SELECT COUNT(*)
            FROM history_images AS image
            WHERE image.batch_id = generation_batches.id AND image.role = 'generated'
        )
        WHERE generated_count IS NULL AND status IN ('completed', 'failed')
        """
    )
    await connection.execute(
        """
        UPDATE generation_batches
        SET status = 'failed',
            error_code = 'partial_generation',
            error_message = printf(
                '本次请求 %d 张，服务商只返回 %d 张，其余 %d 张生成失败',
                image_count, generated_count, image_count - generated_count
            )
        WHERE status = 'completed'
          AND generated_count IS NOT NULL
          AND generated_count < image_count
        """
    )
    await connection.execute(
        """
        UPDATE generation_tasks
        SET status = 'failed',
            error_code = 'partial_generation',
            error_message = (
                SELECT batch.error_message
                FROM generation_batches AS batch
                WHERE batch.task_id = generation_tasks.id
                  AND batch.error_code = 'partial_generation'
                ORDER BY batch.id DESC
                LIMIT 1
            )
        WHERE status = 'completed'
          AND EXISTS (
              SELECT 1
              FROM generation_batches AS batch
              WHERE batch.task_id = generation_tasks.id
                AND batch.error_code = 'partial_generation'
          )
        """
    )
    if {"kind", "status", "error_code", "error_message"}.issubset(history_columns):
        await connection.execute(
            """
            UPDATE history
            SET status = 'failed',
                error_code = 'partial_generation',
                error_message = (
                    SELECT latest.error_message
                    FROM generation_batches AS latest
                    WHERE latest.history_id = history.id
                    ORDER BY latest.id DESC
                    LIMIT 1
                )
            WHERE kind = 'generate'
              AND status = 'completed'
              AND (
                  SELECT latest.error_code
                  FROM generation_batches AS latest
                  WHERE latest.history_id = history.id
                  ORDER BY latest.id DESC
                  LIMIT 1
              ) = 'partial_generation'
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
    await _migrate_skills(connection)
    await _migrate_prompts(connection)


async def _migrate_email_auth(connection: aiosqlite.Connection) -> None:
    tables = {
        row[0]
        for row in await (await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )).fetchall()
    }
    if "users" not in tables:
        return
    user_columns = {
        row[1]
        for row in await (await connection.execute("PRAGMA table_info(users)")).fetchall()
    }
    additions = {
        "email": "TEXT",
        "email_verified_at": "TEXT",
        "is_admin": "INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1))",
        "last_login_at": "TEXT",
        "last_activity_at": "TEXT",
    }
    for column, definition in additions.items():
        if column not in user_columns:
            await connection.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
    await connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique "
        "ON users(lower(email)) WHERE email IS NOT NULL"
    )
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verification_codes (
            email TEXT PRIMARY KEY COLLATE NOCASE,
            code_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            last_sent_at TEXT NOT NULL,
            failed_attempts INTEGER NOT NULL DEFAULT 0
        )
        """
    )


async def _migrate_grok_provider(connection: aiosqlite.Connection) -> None:
    table = await (await connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'api_key_configs'"
    )).fetchone()
    if table is None:
        return
    if "'grok'" in str(table[0]):
        return

    tables = {
        row[0]
        for row in await (await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )).fetchall()
    }
    missing_config_links: set[int] = set()
    if "generation_batches" in tables:
        missing_config_links = {
            int(row[0])
            for row in await (await connection.execute(
                """
                SELECT batch.id
                FROM generation_batches AS batch
                LEFT JOIN api_key_configs AS config ON config.id = batch.api_key_config_id
                WHERE batch.api_key_config_id IS NOT NULL AND config.id IS NULL
                """
            )).fetchall()
        }

    await connection.commit()
    await connection.execute("PRAGMA foreign_keys = OFF")
    await connection.executescript(
        """
        BEGIN;
        CREATE TABLE api_key_configs_v9 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            alias TEXT NOT NULL,
            api_key TEXT NOT NULL DEFAULT '',
            provider_type TEXT NOT NULL CHECK (provider_type IN ('gpt', 'gemini', 'grok')),
            model TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, alias)
        );
        INSERT INTO api_key_configs_v9 (
            id, user_id, alias, api_key, provider_type, model, created_at, updated_at
        )
        SELECT id, user_id, alias, api_key, provider_type, model, created_at, updated_at
        FROM api_key_configs;
        DROP TABLE api_key_configs;
        ALTER TABLE api_key_configs_v9 RENAME TO api_key_configs;
        COMMIT;
        """
    )
    if "generation_batches" in tables:
        migrated_missing_config_links = {
            int(row[0])
            for row in await (await connection.execute(
                """
                SELECT batch.id
                FROM generation_batches AS batch
                LEFT JOIN api_key_configs AS config ON config.id = batch.api_key_config_id
                WHERE batch.api_key_config_id IS NOT NULL AND config.id IS NULL
                """
            )).fetchall()
        }
        if migrated_missing_config_links != missing_config_links:
            raise RuntimeError("Grok provider migration changed API key configuration links")
    await connection.execute("PRAGMA foreign_keys = ON")


async def _migrate_skills(connection: aiosqlite.Connection) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL CHECK (category IN ('portrait', 'product', 'marketing', 'illustration', 'other')),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'pending', 'published', 'rejected')),
            workflow_json TEXT NOT NULL,
            cover_mime_type TEXT,
            cover_data BLOB,
            moderation_note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS skill_favorites (
            skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (skill_id, user_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS skill_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_skills_status_updated
        ON skills(status, updated_at DESC, id DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_skills_user_updated
        ON skills(user_id, updated_at DESC, id DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_skill_uses_skill
        ON skill_uses(skill_id, created_at DESC)
        """,
    ]
    for statement in statements:
        await connection.execute(statement)


async def _migrate_prompts(connection: aiosqlite.Connection) -> None:
    existing = await (await connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'prompt_entries'"
    )).fetchone()
    existing_sql = str(existing[0] or "") if existing else ""
    if "CATEGORY IN" in existing_sql.upper():
        await connection.execute("ALTER TABLE prompt_entries RENAME TO prompt_entries_legacy")
        await connection.execute(
            """
            CREATE TABLE prompt_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await connection.execute(
            """
            INSERT INTO prompt_entries (id, user_id, name, prompt, category, created_at, updated_at)
            SELECT id, user_id, name, prompt, COALESCE(TRIM(category), ''), created_at, updated_at
            FROM prompt_entries_legacy
            """
        )
        await connection.execute("DROP TABLE prompt_entries_legacy")
    else:
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS prompt_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                prompt TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    statements = [
        """
        CREATE INDEX IF NOT EXISTS idx_prompt_entries_user_updated
        ON prompt_entries(user_id, updated_at DESC, id DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_prompt_entries_user_category
        ON prompt_entries(user_id, category)
        """,
    ]
    for statement in statements:
        await connection.execute(statement)


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
            await _migrate_generation_tasks(connection)
            await _migrate_email_auth(connection)
            await _migrate_grok_provider(connection)
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
                    provider_type TEXT NOT NULL CHECK (provider_type IN ('gpt', 'gemini', 'grok')),
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
            await _migrate_generation_tasks(connection)
            await _migrate_email_auth(connection)
            await _migrate_grok_provider(connection)
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
            await _migrate_generation_tasks(connection)
            await _migrate_email_auth(connection)
            await _migrate_grok_provider(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 6:
            await connection.execute("BEGIN")
            await _remove_empty_default_api_key_configs(connection)
            await _migrate_generation_batches(connection)
            await _migrate_generation_tasks(connection)
            await _migrate_email_auth(connection)
            await _migrate_grok_provider(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 7:
            await connection.execute("BEGIN")
            await _migrate_generation_batches(connection)
            await _migrate_generation_tasks(connection)
            await _migrate_email_auth(connection)
            await _migrate_grok_provider(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 8:
            await connection.execute("BEGIN")
            await _migrate_generation_batches(connection)
            await _migrate_generation_tasks(connection)
            await _migrate_email_auth(connection)
            await _migrate_grok_provider(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 9:
            await _migrate_generation_batches(connection)
            await _migrate_generation_tasks(connection)
            await _migrate_grok_provider(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        elif version < 10:
            await _migrate_generation_batches(connection)
            await _migrate_generation_tasks(connection)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        else:
            await connection.executescript(SCHEMA)
            await _migrate_generation_batches(connection)
            await _migrate_generation_tasks(connection)
            await _migrate_email_auth(connection)
            await _migrate_grok_provider(connection)
        await _migrate_skills(connection)
        await _migrate_prompts(connection)
        await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await connection.commit()
