from pathlib import Path

import aiosqlite

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "genimage.db"
FIXED_PROVIDER_NAME = "北海AI"
FIXED_BASE_URL = "https://sub.beibeihai.xyz/v1"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    provider_name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('generate', 'analyze')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'completed', 'failed')),
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    detail TEXT NOT NULL,
    image_count INTEGER NOT NULL DEFAULT 1,
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
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_images_history_id
    ON history_images(history_id, position);
"""


async def initialize_database(
    path: Path = DATABASE_PATH,
    default_model: str = "gpt-image-1.5",
    default_api_key: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as connection:
        await connection.executescript(SCHEMA)
        await connection.execute(
            """
            INSERT OR IGNORE INTO settings
                (id, provider_name, base_url, model, api_key)
            VALUES (1, ?, ?, ?, ?)
            """,
            (
                FIXED_PROVIDER_NAME,
                FIXED_BASE_URL,
                default_model,
                default_api_key,
            ),
        )
        await connection.commit()
