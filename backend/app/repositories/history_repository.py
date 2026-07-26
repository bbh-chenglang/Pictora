from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.history import (
    HistoryDetail,
    HistoryImageMeta,
    HistoryImageRole,
    HistoryKind,
    HistoryStatus,
    HistorySummary,
)


@dataclass(frozen=True)
class StoredHistoryImage:
    id: int
    history_id: int
    mime_type: str
    filename: str | None
    data: bytes


class HistoryRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def create(
        self,
        *,
        kind: HistoryKind,
        prompt: str,
        provider: str,
        model: str,
        detail: str,
        image_count: int,
        size: str | None = None,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                INSERT INTO history
                    (kind, status, prompt, provider, model, detail, image_count, size)
                VALUES (?, 'pending', ?, ?, ?, ?, ?, ?)
                """,
                (kind, prompt, provider, model, detail, image_count, size),
            )
            await connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create history record")
            return cursor.lastrowid

    async def add_image(
        self,
        *,
        history_id: int,
        role: HistoryImageRole,
        mime_type: str,
        filename: str | None,
        position: int,
        data: bytes,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                INSERT INTO history_images
                    (history_id, role, mime_type, filename, position, data)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (history_id, role, mime_type, filename, position, data),
            )
            await connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to store history image")
            return cursor.lastrowid

    async def complete(
        self,
        history_id: int,
        *,
        elapsed_ms: int | None = None,
        analysis_text: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                """
                UPDATE history
                SET status = 'completed',
                    elapsed_ms = ?,
                    analysis_text = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (elapsed_ms, analysis_text, history_id),
            )
            await connection.commit()

    async def fail(
        self,
        history_id: int,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                """
                UPDATE history
                SET status = 'failed',
                    error_code = ?,
                    error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (error_code, error_message, history_id),
            )
            await connection.commit()

    async def list(self, *, limit: int = 50) -> list[HistorySummary]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, kind, status, prompt, provider, model, detail,
                       image_count, size, elapsed_ms, error_code, error_message,
                       created_at
                FROM history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
        return [HistorySummary.model_validate(dict(row)) for row in rows]

    async def get(self, history_id: int) -> HistoryDetail | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, kind, status, prompt, provider, model, detail,
                       image_count, size, analysis_text, elapsed_ms, error_code,
                       error_message, created_at, completed_at
                FROM history
                WHERE id = ?
                """,
                (history_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            image_cursor = await connection.execute(
                """
                SELECT id, role, mime_type, filename, position
                FROM history_images
                WHERE history_id = ?
                ORDER BY position, id
                """,
                (history_id,),
            )
            image_rows = await image_cursor.fetchall()

        images = [
            HistoryImageMeta(
                **dict(image_row),
                url=f"/api/history/{history_id}/images/{image_row['id']}",
            )
            for image_row in image_rows
        ]
        return HistoryDetail.model_validate({**dict(row), "images": images})

    async def get_image(
        self,
        history_id: int,
        image_id: int,
    ) -> StoredHistoryImage | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, history_id, mime_type, filename, data
                FROM history_images
                WHERE history_id = ? AND id = ?
                """,
                (history_id, image_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return StoredHistoryImage(**dict(row))
