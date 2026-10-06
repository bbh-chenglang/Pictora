import sqlite3
import aiosqlite

VIDEO_SCHEMA = """
-- Valid legacy databases already have this table; minimal older snapshots may not.
CREATE TABLE IF NOT EXISTS projects (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,name)
);
CREATE TABLE IF NOT EXISTS video_api_key_configs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 alias TEXT NOT NULL, api_key TEXT NOT NULL, model TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(user_id, alias)
);
CREATE TABLE IF NOT EXISTS video_preferences (
 user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
 active_config_id INTEGER REFERENCES video_api_key_configs(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS video_assets (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 type TEXT NOT NULL, name TEXT NOT NULL, filename TEXT NOT NULL,
 mime_type TEXT NOT NULL, byte_size INTEGER NOT NULL, duration_seconds REAL,
 relative_path TEXT NOT NULL, ever_referenced INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS video_tasks (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 api_key_config_id INTEGER REFERENCES video_api_key_configs(id) ON DELETE SET NULL,
 request_id TEXT NOT NULL, request_json TEXT NOT NULL, payload_json TEXT NOT NULL,
 model TEXT NOT NULL, prompt TEXT NOT NULL, duration INTEGER NOT NULL,
 resolution TEXT NOT NULL, ratio TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', upstream_task_id TEXT, upstream_status TEXT,
 progress REAL, error_code TEXT, error_message TEXT, tracking_abandoned INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, started_at TEXT, completed_at TEXT,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(user_id, request_id), UNIQUE(user_id, upstream_task_id)
);
CREATE TABLE IF NOT EXISTS video_task_assets (
 task_id INTEGER NOT NULL REFERENCES video_tasks(id) ON DELETE CASCADE,
 asset_id TEXT NOT NULL REFERENCES video_assets(id) ON DELETE RESTRICT,
 PRIMARY KEY(task_id, asset_id)
);
CREATE TABLE IF NOT EXISTS video_results (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 task_id INTEGER NOT NULL REFERENCES video_tasks(id) ON DELETE CASCADE,
 position INTEGER NOT NULL, object_key TEXT NOT NULL,
 filename TEXT NOT NULL, byte_size INTEGER, duration_seconds REAL,
 mime_type TEXT NOT NULL DEFAULT 'video/mp4', stored INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(task_id, position)
);
CREATE TABLE IF NOT EXISTS video_storage_cleanup (
 id INTEGER PRIMARY KEY AUTOINCREMENT, object_key TEXT NOT NULL UNIQUE,
 attempts INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_video_tasks_user_project ON video_tasks(user_id, project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_video_tasks_status ON video_tasks(status);
CREATE INDEX IF NOT EXISTS idx_video_assets_user ON video_assets(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_video_task_assets_asset ON video_task_assets(asset_id);
CREATE TRIGGER IF NOT EXISTS protect_tracked_video_project BEFORE DELETE ON projects
WHEN EXISTS (SELECT 1 FROM video_tasks WHERE project_id=OLD.id AND tracking_abandoned=0
 AND status IN ('queued','submitting','running','saving','polling_paused','submission_unknown','storage_failed'))
BEGIN SELECT RAISE(ABORT, 'video_project_tracking'); END;
CREATE TRIGGER IF NOT EXISTS queue_video_result_cleanup BEFORE DELETE ON video_results
BEGIN INSERT OR IGNORE INTO video_storage_cleanup(object_key) VALUES(OLD.object_key); END;
"""

async def migrate_video(connection: aiosqlite.Connection) -> None:
    # execute individual statements: executescript would commit the enclosing migration.
    statement = ""
    for line in VIDEO_SCHEMA.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            await connection.execute(statement)
            statement = ""

    columns = {row[1] for row in await (await connection.execute("PRAGMA table_info(video_assets)")).fetchall()}
    if "ever_referenced" not in columns:
        await connection.execute("ALTER TABLE video_assets ADD COLUMN ever_referenced INTEGER NOT NULL DEFAULT 0")
        await connection.execute("UPDATE video_assets SET ever_referenced=1 WHERE id IN (SELECT asset_id FROM video_task_assets)")
