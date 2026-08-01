from pathlib import Path

import aiosqlite

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "genimage.db"
FIXED_PROVIDER_NAME = "北海AI"
FIXED_BASE_URL = "https://sub.beibeihai.xyz/v1"
SCHEMA_VERSION = 3

SCHEMA = f"""
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT 'gpt-image-1.5',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    analysis_text TEXT,
    elapsed_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS history_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('reference', 'generated')),
    mime_type TEXT NOT NULL,
    filename TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    data BLOB NOT NULL
);
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
                    detail, image_count, size, analysis_text, elapsed_ms, error_code,
                    error_message, created_at, completed_at
                )
                SELECT h.id, h.user_id, p.id, h.kind, h.status, h.prompt, h.provider,
                       h.model, h.detail, h.image_count, h.size, h.analysis_text,
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
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            await connection.commit()
            return
        else:
            await connection.executescript(SCHEMA)
        await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        await connection.commit()
