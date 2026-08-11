from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.history import (
    HistoryDetail,
    HistoryImageEditReference,
    HistoryImageEditSnapshot,
    HistoryImageMeta,
    HistoryImageRole,
    HistoryKind,
    HistoryStatus,
    HistorySummary,
    ReferenceCategory,
)


@dataclass(frozen=True)
class StoredHistoryImage:
    id: int
    history_id: int
    mime_type: str
    filename: str | None
    data: bytes


class HistoryConversationNotFoundError(Exception):
    pass


class HistoryConversationBusyError(Exception):
    pass


class HistoryRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    @staticmethod
    async def _insert_generation_batch(
        connection: aiosqlite.Connection,
        *,
        history_id: int,
        user_id: int,
        api_key_config_id: int | None,
        prompt: str,
        provider: str,
        model: str,
        detail: str,
        image_count: int,
        size: str | None,
        resolution: str | None,
    ) -> int:
        stored_config_id = None
        if api_key_config_id is not None:
            config = await (await connection.execute(
                "SELECT id FROM api_key_configs WHERE id = ? AND user_id = ?",
                (api_key_config_id, user_id),
            )).fetchone()
            stored_config_id = int(config[0]) if config is not None else None
        cursor = await connection.execute(
            """
            INSERT INTO generation_batches (
                history_id, api_key_config_id, prompt, provider, model, detail,
                image_count, size, resolution
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id, stored_config_id, prompt, provider, model, detail,
                image_count, size, resolution,
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to create generation batch")
        return cursor.lastrowid

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
        api_key_config_id: int | None = None,
        size: str | None = None,
        resolution: str | None = None,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
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
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create history record")
            history_id = cursor.lastrowid
            await self._insert_generation_batch(
                connection,
                history_id=history_id,
                user_id=user_id,
                api_key_config_id=api_key_config_id,
                prompt=prompt,
                provider=provider,
                model=model,
                detail=detail,
                image_count=image_count,
                size=size,
                resolution=resolution,
            )
            await connection.commit()
            return history_id

    async def restart_generation(
        self,
        history_id: int,
        *,
        user_id: int,
        project_id: int,
        prompt: str,
        provider: str,
        model: str,
        detail: str,
        image_count: int,
        api_key_config_id: int | None = None,
        size: str | None = None,
        resolution: str | None = None,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT status FROM history
                WHERE id = ? AND user_id = ? AND project_id = ? AND kind = 'generate'
                """,
                (history_id, user_id, project_id),
            )
            row = await cursor.fetchone()
            if row is None:
                await connection.rollback()
                raise HistoryConversationNotFoundError(history_id)
            if row[0] == "pending":
                await connection.rollback()
                raise HistoryConversationBusyError(history_id)
            await connection.execute(
                """
                UPDATE history
                SET status = 'pending',
                    prompt = ?, provider = ?, model = ?, detail = ?,
                    image_count = ?, size = ?, resolution = ?,
                    analysis_text = NULL, elapsed_ms = NULL,
                    error_code = NULL, error_message = NULL,
                    completed_at = NULL, created_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    prompt,
                    provider,
                    model,
                    detail,
                    image_count,
                    size,
                    resolution,
                    history_id,
                ),
            )
            batch_id = await self._insert_generation_batch(
                connection,
                history_id=history_id,
                user_id=user_id,
                api_key_config_id=api_key_config_id,
                prompt=prompt,
                provider=provider,
                model=model,
                detail=detail,
                image_count=image_count,
                size=size,
                resolution=resolution,
            )
            await connection.commit()
            return batch_id

    async def latest_generation_batch_id(self, *, user_id: int, history_id: int) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            row = await (await connection.execute(
                """
                SELECT batch.id
                FROM generation_batches AS batch
                JOIN history ON history.id = batch.history_id
                WHERE batch.history_id = ? AND history.user_id = ?
                ORDER BY batch.id DESC
                LIMIT 1
                """,
                (history_id, user_id),
            )).fetchone()
        if row is None:
            raise HistoryConversationNotFoundError(history_id)
        return int(row[0])

    async def next_image_position(
        self,
        *,
        user_id: int,
        history_id: int,
        role: HistoryImageRole,
        batch_id: int | None = None,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                SELECT COALESCE(MAX(image.position), -1) + 1
                FROM history_images AS image
                JOIN history ON history.id = image.history_id
                WHERE image.history_id = ? AND image.role = ? AND history.user_id = ?
                  AND (? IS NULL OR image.batch_id = ?)
                """,
                (history_id, role, user_id, batch_id, batch_id),
            )
            row = await cursor.fetchone()
        return int(row[0]) if row is not None else 0

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
        batch_id: int | None = None,
        reference_category: ReferenceCategory | None = None,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            if batch_id is None:
                row = await (await connection.execute(
                    """
                    SELECT batch.id
                    FROM generation_batches AS batch
                    JOIN history ON history.id = batch.history_id
                    WHERE batch.history_id = ? AND history.user_id = ?
                    ORDER BY batch.id DESC
                    LIMIT 1
                    """,
                    (history_id, user_id),
                )).fetchone()
                batch_id = int(row[0]) if row is not None else None
            category = (reference_category or "person") if role == "reference" else None
            cursor = await connection.execute(
                """
                INSERT INTO history_images
                    (history_id, batch_id, role, reference_category, mime_type, filename, position, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (history_id, batch_id, role, category, mime_type, filename, position, data),
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
                SELECT image.id, image.role, image.mime_type, image.filename,
                       image.position, image.reference_category
                FROM history_images AS image
                WHERE image.history_id = ?
                  AND (
                      image.role = 'generated'
                      OR image.batch_id = (
                          SELECT batch.id
                          FROM generation_batches AS batch
                          WHERE batch.history_id = image.history_id
                          ORDER BY batch.id DESC
                          LIMIT 1
                      )
                  )
                ORDER BY CASE image.role WHEN 'reference' THEN 0 ELSE 1 END,
                         image.batch_id, image.position, image.id
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

    async def get_image_edit_snapshot(
        self,
        user_id: int,
        history_id: int,
        image_id: int,
    ) -> HistoryImageEditSnapshot | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT image.batch_id, config.id AS api_key_config_id, batch.prompt,
                       batch.provider, batch.model, batch.detail, batch.image_count,
                       batch.size, batch.resolution
                FROM history_images AS image
                JOIN history ON history.id = image.history_id
                JOIN generation_batches AS batch ON batch.id = image.batch_id
                LEFT JOIN api_key_configs AS config
                  ON config.id = batch.api_key_config_id AND config.user_id = history.user_id
                WHERE image.history_id = ? AND image.id = ?
                  AND image.role = 'generated' AND history.user_id = ?
                """,
                (history_id, image_id, user_id),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            reference_cursor = await connection.execute(
                """
                SELECT id, mime_type, filename, position,
                       COALESCE(reference_category, 'person') AS category
                FROM history_images
                WHERE history_id = ? AND batch_id = ? AND role = 'reference'
                ORDER BY position, id
                """,
                (history_id, row["batch_id"]),
            )
            reference_rows = await reference_cursor.fetchall()

        references = [
            HistoryImageEditReference(
                **dict(reference_row),
                url=f"/api/history/{history_id}/images/{reference_row['id']}",
            )
            for reference_row in reference_rows
        ]
        values = dict(row)
        values.pop("batch_id", None)
        return HistoryImageEditSnapshot(
            history_id=history_id,
            image_id=image_id,
            references=references,
            **values,
        )

    async def delete_generated_image(
        self,
        user_id: int,
        history_id: int,
        image_id: int,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            cursor = await connection.execute(
                """
                DELETE FROM history_images
                WHERE id = ? AND history_id = ? AND role = 'generated'
                  AND EXISTS (
                      SELECT 1 FROM history
                      WHERE history.id = history_images.history_id AND history.user_id = ?
                  )
                """,
                (image_id, history_id, user_id),
            )
            await connection.commit()
        return cursor.rowcount > 0
