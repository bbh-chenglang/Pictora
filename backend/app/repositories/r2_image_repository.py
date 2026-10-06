"""Durable outbox for *new generated* images. Never scans historical images."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time
from uuid import uuid4

import aiosqlite


@dataclass(frozen=True)
class R2ImageDestination:
    endpoint: str
    bucket: str
    prefix: str = "pictora/generated"


SCHEMA = """
CREATE TABLE IF NOT EXISTS r2_image_uploads (
    id TEXT PRIMARY KEY,
    image_id INTEGER UNIQUE REFERENCES history_images(id) ON DELETE SET NULL,
    endpoint TEXT NOT NULL,
    bucket TEXT NOT NULL,
    object_key TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'uploading', 'ready', 'retry', 'deleted')),
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    lease_id TEXT,
    lease_until REAL NOT NULL DEFAULT 0,
    last_error_code TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_r2_image_uploads_due
    ON r2_image_uploads(status, next_attempt_at, lease_until);
"""


async def enqueue_new_image(
    connection: aiosqlite.Connection,
    destination: R2ImageDestination,
    *, image_id: int, mime_type: str, data: bytes,
) -> None:
    """Called inside the same transaction that inserts a generated image."""
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime_type, "bin")
    key = f"{destination.prefix.strip('/')}/{datetime.now(timezone.utc):%Y/%m/%d}/{uuid4().hex}.{extension}"
    await connection.execute(
        """INSERT INTO r2_image_uploads
           (id, image_id, endpoint, bucket, object_key, mime_type, size_bytes, sha256)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (uuid4().hex, image_id, destination.endpoint, destination.bucket, key,
         mime_type, len(data), hashlib.sha256(data).hexdigest()),
    )


class R2ImageRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def claim(self, destination: R2ImageDestination, *, now: float | None = None) -> dict | None:
        now = time.time() if now is None else now
        async with aiosqlite.connect(self.database_path, timeout=15) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("BEGIN IMMEDIATE")
            row = await (await db.execute(
                """SELECT job.*, image.data
                   FROM r2_image_uploads AS job
                   LEFT JOIN history_images AS image ON image.id = job.image_id
                   WHERE job.endpoint = ? AND job.bucket = ?
                     AND job.status != 'deleted' AND job.next_attempt_at <= ?
                     AND (
                         job.status IN ('pending', 'retry')
                         OR (job.status = 'uploading' AND job.lease_until <= ?)
                         OR (job.status = 'ready' AND job.image_id IS NULL)
                     )
                   ORDER BY job.next_attempt_at, job.created_at, job.id LIMIT 1""",
                (destination.endpoint, destination.bucket, now, now),
            )).fetchone()
            if row is None:
                await db.rollback()
                return None
            job = dict(row)
            job['lease_id'] = uuid4().hex
            job['attempts'] += 1
            await db.execute(
                """UPDATE r2_image_uploads SET status = 'uploading', attempts = ?,
                   lease_id = ?, lease_until = ? WHERE id = ?""",
                (job['attempts'], job['lease_id'], now + 300, job['id']),
            )
            await db.commit()
            return job

    async def complete(self, job: dict, *, deleted: bool = False) -> None:
        async with aiosqlite.connect(self.database_path) as db:
            # A deletion while uploading detaches image_id. Queue cleanup instead
            # of publishing an object whose original record no longer exists.
            await db.execute(
                """UPDATE r2_image_uploads
                   SET status = CASE WHEN ? THEN 'deleted'
                                     WHEN image_id IS NULL THEN 'retry' ELSE 'ready' END,
                       next_attempt_at = 0, lease_id = NULL, lease_until = 0,
                       last_error_code = NULL, verified_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND lease_id = ?""",
                (deleted, job['id'], job['lease_id']),
            )
            await db.commit()

    async def retry(self, job: dict, error_code: str) -> None:
        delay = min(3600, 5 * 2 ** min(job['attempts'], 10))
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute(
                """UPDATE r2_image_uploads SET status = 'retry', next_attempt_at = ?,
                   lease_id = NULL, lease_until = 0, last_error_code = ?
                   WHERE id = ? AND lease_id = ?""",
                (time.time() + delay, error_code, job['id'], job['lease_id']),
            )
            await db.commit()

    async def ready_for_image(self, image_id: int, destination: R2ImageDestination) -> dict | None:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute(
                """SELECT job.* FROM r2_image_uploads AS job
                   JOIN history_images AS image ON image.id = job.image_id
                   WHERE job.image_id = ? AND job.status = 'ready'
                     AND job.endpoint = ? AND job.bucket = ?""",
                (image_id, destination.endpoint, destination.bucket),
            )).fetchone()
            return dict(row) if row else None
