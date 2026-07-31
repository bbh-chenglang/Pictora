from pathlib import Path

import aiosqlite

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "genimage.db"
FIXED_PROVIDER_NAME = "北海AI"
FIXED_BASE_URL = "https://sub.beibeihai.xyz/v1"
SCHEMA_VERSION = 2

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
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
CREATE INDEX IF NOT EXISTS idx_history_images_history_id ON history_images(history_id, position);
"""


async def initialize_database(path: Path = DATABASE_PATH, **_: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as connection:
        await connection.execute("PRAGMA foreign_keys = ON")
        cursor = await connection.execute("PRAGMA user_version")
        version = (await cursor.fetchone())[0]
        if version < SCHEMA_VERSION:
            await connection.execute("DROP TABLE IF EXISTS history_images")
            await connection.execute("DROP TABLE IF EXISTS history")
            await connection.execute("DROP TABLE IF EXISTS settings")
            await connection.executescript(SCHEMA)
            await connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        else:
            await connection.executescript(SCHEMA)
        await connection.commit()
