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
        user_id: int,
        project_id: int | None = None,
        kind: HistoryKind,
        prompt: str,
        provider: str,
        model: str,
        detail: str,
        image_count: int,
        size: str | None = None,
        resolution: str | None = None,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            if project_id is None:
                project_cursor = await connection.execute(
                    """
                    SELECT id FROM projects
                    WHERE user_id = ?
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
                project_row = await project_cursor.fetchone()
                if project_row is None:
                    raise ValueError("User has no project")
                project_id = project_row[0]
            cursor = await connection.execute(
                """
                INSERT INTO history
                    (user_id, project_id, kind, status, prompt, provider, model, detail, image_count, size, resolution)
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, project_id, kind, prompt, provider, model, detail, image_count, size, resolution),
            )
            await connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create history record")
            return cursor.lastrowid

    async def add_image(
        self,
        *,
        user_id: int,
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
                WHERE id = ? AND status = 'pending'
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
                WHERE id = ? AND status = 'pending'
                """,
                (error_code, error_message, history_id),
            )
            await connection.commit()

    async def fail_pending_generations(
        self,
        *,
        error_code: str = "generation_interrupted",
        error_message: str = "服务重启导致任务中断，请重新生成",
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                UPDATE history
                SET status = 'failed',
                    error_code = ?,
                    error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE kind = 'generate' AND status = 'pending'
                """,
                (error_code, error_message),
            )
            await connection.commit()
        return cursor.rowcount

    async def list(self, *, user_id: int, limit: int = 50) -> list[HistorySummary]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, kind, status, prompt, provider, model, detail,
                       image_count, size, resolution, elapsed_ms, error_code, error_message,
                       created_at
                FROM history
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
        return [HistorySummary.model_validate(dict(row)) for row in rows]

    async def get_project_id(self, user_id: int, history_id: int) -> int | None:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                "SELECT project_id FROM history WHERE id = ? AND user_id = ?",
                (history_id, user_id),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row is not None else None

    async def get(self, user_id: int, history_id: int) -> HistoryDetail | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, kind, status, prompt, provider, model, detail,
                       image_count, size, resolution, analysis_text, elapsed_ms, error_code,
                       error_message, created_at, completed_at
                FROM history
                WHERE id = ? AND user_id = ?
                """,
                (history_id, user_id),
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
        user_id: int,
        history_id: int,
        image_id: int,
    ) -> StoredHistoryImage | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT image.id, image.history_id, image.mime_type, image.filename, image.data
                FROM history_images AS image
                JOIN history ON history.id = image.history_id
                WHERE image.history_id = ? AND image.id = ? AND history.user_id = ?
                """,
                (history_id, image_id, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return StoredHistoryImage(**dict(row))
