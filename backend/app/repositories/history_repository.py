from dataclasses import dataclass
import json
from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.common import GenerationViewSpec
from app.schemas.history import (
    GenerationBatchDetail,
    GenerationBatchSummary,
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


def _encode_generation_views(views: list[GenerationViewSpec] | None) -> str | None:
    if not views:
        return None
    return json.dumps(
        [view.model_dump() for view in views],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _decode_generation_views(value: str | None) -> list[GenerationViewSpec]:
    if not value:
        return []
    try:
        payload = json.loads(value)
        if not isinstance(payload, list):
            return []
        return [GenerationViewSpec.model_validate(item) for item in payload]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


@dataclass(frozen=True)
class StoredHistoryImage:
    id: int
    history_id: int
    mime_type: str
    filename: str | None
    data: bytes


class HistoryConversationNotFoundError(Exception):
    pass


class GenerationTaskNotFoundError(Exception):
    pass


class GenerationTaskNotRunnableError(Exception):
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
        output_format: str | None,
        background: str | None,
        output_compression: int | None,
        moderation: str | None,
        views: list[GenerationViewSpec] | None,
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
                image_count, size, resolution, output_format, background,
                output_compression, moderation, views_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id, stored_config_id, prompt, provider, model, detail,
                image_count, size, resolution, output_format, background,
                output_compression, moderation, _encode_generation_views(views),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to create generation batch")
        return cursor.lastrowid

    @staticmethod
    async def _refresh_generation_history_status(
        connection: aiosqlite.Connection,
        history_id: int,
    ) -> None:
        await connection.execute(
            """
            UPDATE history
            SET status = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM generation_batches
                        WHERE history_id = :history_id AND status = 'pending'
                    ) THEN 'pending'
                    ELSE COALESCE((
                        SELECT status FROM generation_batches
                        WHERE history_id = :history_id
                        ORDER BY id DESC LIMIT 1
                    ), status)
                END,
                elapsed_ms = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM generation_batches
                        WHERE history_id = :history_id AND status = 'pending'
                    ) THEN NULL
                    ELSE (
                        SELECT elapsed_ms FROM generation_batches
                        WHERE history_id = :history_id
                        ORDER BY id DESC LIMIT 1
                    )
                END,
                error_code = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM generation_batches
                        WHERE history_id = :history_id AND status = 'pending'
                    ) THEN NULL
                    ELSE (
                        SELECT error_code FROM generation_batches
                        WHERE history_id = :history_id
                        ORDER BY id DESC LIMIT 1
                    )
                END,
                error_message = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM generation_batches
                        WHERE history_id = :history_id AND status = 'pending'
                    ) THEN NULL
                    ELSE (
                        SELECT error_message FROM generation_batches
                        WHERE history_id = :history_id
                        ORDER BY id DESC LIMIT 1
                    )
                END,
                completed_at = CASE
                    WHEN EXISTS (
                        SELECT 1 FROM generation_batches
                        WHERE history_id = :history_id AND status = 'pending'
                    ) THEN NULL
                    ELSE (
                        SELECT completed_at FROM generation_batches
                        WHERE history_id = :history_id
                        ORDER BY id DESC LIMIT 1
                    )
                END
            WHERE id = :history_id AND kind = 'generate'
            """,
            {"history_id": history_id},
        )

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
        output_format: str | None = None,
        background: str | None = None,
        output_compression: int | None = None,
        moderation: str | None = None,
        views: list[GenerationViewSpec] | None = None,
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
                output_format=output_format,
                background=background,
                output_compression=output_compression,
                moderation=moderation,
                views=views,
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
        output_format: str | None = None,
        background: str | None = None,
        output_compression: int | None = None,
        moderation: str | None = None,
        views: list[GenerationViewSpec] | None = None,
    ) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                """
                SELECT id FROM history
                WHERE id = ? AND user_id = ? AND project_id = ? AND kind = 'generate'
                """,
                (history_id, user_id, project_id),
            )
            row = await cursor.fetchone()
            if row is None:
                await connection.rollback()
                raise HistoryConversationNotFoundError(history_id)
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
                output_format=output_format,
                background=background,
                output_compression=output_compression,
                moderation=moderation,
                views=views,
            )
            await connection.commit()
            return batch_id

    async def get_generation_batch(
        self,
        user_id: int,
        history_id: int,
        batch_id: int,
    ) -> GenerationBatchDetail | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            row = await (await connection.execute(
                """
                SELECT batch.id, batch.history_id, batch.status, batch.image_count,
                       COALESCE(batch.generated_count, (
                           SELECT COUNT(*) FROM history_images AS image
                           WHERE image.batch_id = batch.id AND image.role = 'generated'
                       )) AS generated_count, batch.elapsed_ms,
                       batch.error_code, batch.error_message, batch.created_at,
                       batch.views_json
                FROM generation_batches AS batch
                JOIN history ON history.id = batch.history_id
                WHERE batch.id = ? AND batch.history_id = ? AND history.user_id = ?
                """,
                (batch_id, history_id, user_id),
            )).fetchone()
            if row is None:
                return None
            image_rows = await (await connection.execute(
                """
                SELECT id, batch_id, role, mime_type, filename, position,
                       batch_position, reference_category
                FROM history_images
                WHERE history_id = ? AND batch_id = ? AND role = 'generated'
                ORDER BY position, id
                """,
                (history_id, batch_id),
            )).fetchall()
            deleted_rows = await (await connection.execute(
                """
                SELECT position FROM generation_batch_deleted_slots
                WHERE batch_id = ? ORDER BY position
                """,
                (batch_id,),
            )).fetchall()
            cancelled_rows = await (await connection.execute(
                """
                SELECT position FROM generation_batch_cancelled_slots
                WHERE batch_id = ? ORDER BY position
                """,
                (batch_id,),
            )).fetchall()
        images = [
            HistoryImageMeta(
                **dict(image_row),
                url=f"/api/history/{history_id}/images/{image_row['id']}",
            )
            for image_row in image_rows
        ]
        values = dict(row)
        views = _decode_generation_views(values.pop("views_json", None))
        return GenerationBatchDetail.model_validate({
            **values,
            "views": views,
            "images": images,
            "deleted_positions": [int(deleted[0]) for deleted in deleted_rows],
            "cancelled_positions": [int(cancelled[0]) for cancelled in cancelled_rows],
        })

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

    async def create_generation_task(self, *, user_id: int, history_id: int, batch_id: int) -> int:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            cursor = await connection.execute(
                "INSERT INTO generation_tasks (user_id, history_id, status) VALUES (?, ?, 'queued')",
                (user_id, history_id),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create generation task")
            task_id = int(cursor.lastrowid)
            await connection.execute(
                "UPDATE generation_batches SET task_id = ? WHERE id = ? AND history_id = ?",
                (task_id, batch_id, history_id),
            )
            await connection.commit()
        return task_id

    async def get_generation_task(self, user_id: int, task_id: int):
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            row = await (await connection.execute(
                """
                SELECT task.id, task.user_id, task.history_id, history.project_id,
                       task.status, task.attempts, task.error_code, task.error_message,
                       task.created_at, task.started_at, task.completed_at,
                       batch.id AS batch_id, batch.api_key_config_id, batch.prompt,
                       batch.provider, batch.model, batch.detail, batch.image_count,
                       batch.size, batch.resolution, batch.views_json
                FROM generation_tasks AS task
                JOIN history ON history.id = task.history_id
                JOIN generation_batches AS batch ON batch.task_id = task.id
                WHERE task.id = ? AND task.user_id = ?
                ORDER BY batch.id DESC
                LIMIT 1
                """,
                (task_id, user_id),
            )).fetchone()
            if row is None:
                return None
            deleted_rows = await (await connection.execute(
                """
                SELECT position FROM generation_batch_deleted_slots
                WHERE batch_id = ? ORDER BY position
                """,
                (row["batch_id"],),
            )).fetchall()
            cancelled_rows = await (await connection.execute(
                """
                SELECT position FROM generation_batch_cancelled_slots
                WHERE batch_id = ? ORDER BY position
                """,
                (row["batch_id"],),
            )).fetchall()
            image_rows = await (await connection.execute(
                """
                SELECT id, batch_id, role, mime_type, filename, position,
                       batch_position, reference_category
                FROM history_images
                WHERE history_id = ? AND batch_id = ? AND role = 'generated'
                ORDER BY position, id
                """,
                (row["history_id"], row["batch_id"]),
            )).fetchall()
        images = [
            HistoryImageMeta(
                **dict(image_row),
                url=f"/api/history/{row['history_id']}/images/{image_row['id']}",
            )
            for image_row in image_rows
        ]
        values = dict(row)
        views = _decode_generation_views(values.pop("views_json", None))
        return {
            **values,
            "views": views,
            "generated_count": len(images),
            "images": images,
            "deleted_positions": [int(deleted[0]) for deleted in deleted_rows],
            "cancelled_positions": [int(cancelled[0]) for cancelled in cancelled_rows],
        }

    async def list_generation_tasks(self, user_id: int, *, active_only: bool = False) -> list[dict]:
        status_clause = "AND task.status IN ('queued', 'running')" if active_only else ""
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(
                f"""
                SELECT task.id, task.user_id, task.history_id, history.project_id,
                       task.status, task.attempts,
                       task.error_code, task.error_message, task.created_at,
                       task.started_at, task.completed_at,
                       batch.id AS batch_id, batch.api_key_config_id, batch.prompt,
                       batch.provider, batch.model, batch.detail, batch.image_count,
                       batch.size, batch.resolution, batch.views_json
                FROM generation_tasks AS task
                JOIN history ON history.id = task.history_id
                JOIN generation_batches AS batch ON batch.task_id = task.id
                WHERE task.user_id = ? {status_clause}
                ORDER BY task.created_at DESC, task.id DESC
                """,
                (user_id,),
            )).fetchall()
            tasks = []
            for row in rows:
                deleted_rows = await (await connection.execute(
                    """
                    SELECT position FROM generation_batch_deleted_slots
                    WHERE batch_id = ? ORDER BY position
                    """,
                    (row["batch_id"],),
                )).fetchall()
                cancelled_rows = await (await connection.execute(
                    """
                    SELECT position FROM generation_batch_cancelled_slots
                    WHERE batch_id = ? ORDER BY position
                    """,
                    (row["batch_id"],),
                )).fetchall()
                image_rows = await (await connection.execute(
                    """
                    SELECT id, batch_id, role, mime_type, filename, position,
                           batch_position, reference_category
                    FROM history_images
                    WHERE history_id = ? AND batch_id = ? AND role = 'generated'
                    ORDER BY position, id
                    """,
                    (row["history_id"], row["batch_id"]),
                )).fetchall()
                images = [
                    HistoryImageMeta(
                        **dict(image_row),
                        url=f"/api/history/{row['history_id']}/images/{image_row['id']}",
                    )
                    for image_row in image_rows
                ]
                values = dict(row)
                views = _decode_generation_views(values.pop("views_json", None))
                tasks.append({
                    **values,
                    "views": views,
                    "generated_count": len(images),
                    "images": images,
                    "deleted_positions": [int(deleted[0]) for deleted in deleted_rows],
                    "cancelled_positions": [int(cancelled[0]) for cancelled in cancelled_rows],
                })
        return tasks

    async def list_active_generation_task_ids(
        self,
        user_id: int,
        *,
        project_id: int | None = None,
        history_ids: list[int] | None = None,
    ) -> list[int]:
        filters = ["task.user_id = ?", "task.status IN ('queued', 'running')"]
        parameters: list[object] = [user_id]
        if project_id is not None:
            filters.append("history.project_id = ?")
            parameters.append(project_id)
        if history_ids is not None:
            unique_ids = sorted(set(history_ids))
            if not unique_ids:
                return []
            filters.append(f"history.id IN ({','.join('?' for _ in unique_ids)})")
            parameters.extend(unique_ids)
        async with aiosqlite.connect(self.database_path) as connection:
            rows = await (await connection.execute(
                f"""
                SELECT task.id
                FROM generation_tasks AS task
                JOIN history ON history.id = task.history_id
                WHERE {' AND '.join(filters)}
                ORDER BY task.id
                """,
                parameters,
            )).fetchall()
        return [int(row[0]) for row in rows]

    async def _task_batch_id(self, user_id: int, task_id: int) -> int | None:
        async with aiosqlite.connect(self.database_path) as connection:
            row = await (await connection.execute(
                "SELECT batch.id FROM generation_batches AS batch JOIN generation_tasks AS task ON task.id = batch.task_id WHERE task.id = ? AND task.user_id = ? ORDER BY batch.id DESC LIMIT 1",
                (task_id, user_id),
            )).fetchone()
        return int(row[0]) if row is not None else None

    async def mark_generation_task_running(
        self,
        task_id: int,
        user_id: int,
        *,
        worker_id: str,
    ) -> bool:
        return await self.claim_generation_task(task_id, user_id, worker_id=worker_id)

    async def claim_generation_task(
        self,
        task_id: int,
        user_id: int,
        *,
        worker_id: str,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                """
                UPDATE generation_tasks
                SET status = 'running', attempts = attempts + 1,
                    worker_id = ?, heartbeat_at = CURRENT_TIMESTAMP,
                    started_at = COALESCE(started_at, CURRENT_TIMESTAMP)
                WHERE id = ? AND user_id = ? AND status = 'queued'
                """,
                (worker_id, task_id, user_id),
            )
            await connection.commit()
            cursor = await connection.execute("SELECT changes()")
            changed = int((await cursor.fetchone())[0])
        return changed == 1

    async def heartbeat_generation_task(
        self,
        task_id: int,
        user_id: int,
        *,
        worker_id: str,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                UPDATE generation_tasks
                SET heartbeat_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ? AND status = 'running'
                  AND worker_id = ?
                """,
                (task_id, user_id, worker_id),
            )
            await connection.commit()
        return cursor.rowcount == 1

    async def generation_task_is_active(
        self,
        task_id: int,
        user_id: int,
        *,
        worker_id: str,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            row = await (await connection.execute(
                """
                SELECT 1 FROM generation_tasks
                WHERE id = ? AND user_id = ? AND status = 'running'
                  AND worker_id = ?
                """,
                (task_id, user_id, worker_id),
            )).fetchone()
        return row is not None

    async def complete_generation_task(
        self,
        task_id: int,
        user_id: int,
        *,
        worker_id: str,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                UPDATE generation_tasks
                SET status = 'completed', completed_at = CURRENT_TIMESTAMP,
                    error_code = NULL, error_message = NULL
                WHERE id = ? AND user_id = ? AND status IN ('queued', 'running')
                  AND worker_id = ?
                """,
                (task_id, user_id, worker_id),
            )
            await connection.commit()
        return cursor.rowcount == 1

    async def fail_generation_task(
        self,
        task_id: int,
        user_id: int,
        *,
        status: str = "failed",
        error_code: str,
        error_message: str,
        worker_id: str,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                UPDATE generation_tasks
                SET status = ?, error_code = ?, error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ? AND status IN ('queued', 'running')
                  AND worker_id = ?
                """,
                (status, error_code, error_message, task_id, user_id, worker_id),
            )
            await connection.commit()
        return cursor.rowcount == 1

    async def cancel_generation_task(
        self,
        task_id: int,
        user_id: int,
        *,
        error_code: str = "generation_cancelled",
        error_message: str = "生成任务已取消",
    ) -> bool:
        """Cancel one task and its batch without failing sibling batches."""
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            connection.row_factory = aiosqlite.Row
            task = await (await connection.execute(
                """
                SELECT task.id, task.history_id, task.status,
                       (SELECT batch.id FROM generation_batches AS batch
                        WHERE batch.task_id = task.id
                        ORDER BY batch.id DESC LIMIT 1) AS batch_id
                FROM generation_tasks AS task
                WHERE task.id = ? AND task.user_id = ?
                """,
                (task_id, user_id),
            )).fetchone()
            if task is None or task["status"] not in {"queued", "running"}:
                await connection.rollback()
                return False

            history_id = int(task["history_id"])
            batch_id = task["batch_id"]
            await connection.execute(
                """
                UPDATE generation_tasks
                SET status = 'cancelled', error_code = ?, error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ? AND status IN ('queued', 'running')
                """,
                (error_code, error_message, task_id, user_id),
            )
            if batch_id is not None:
                await connection.execute(
                    """
                    UPDATE generation_batches
                    SET status = 'failed', error_code = ?, error_message = ?,
                        generated_count = (
                            SELECT COUNT(*) FROM history_images
                            WHERE batch_id = ? AND role = 'generated'
                        ),
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND history_id = ? AND status = 'pending'
                    """,
                    (error_code, error_message, batch_id, batch_id, history_id),
                )
            await self._refresh_generation_history_status(connection, history_id)
            await connection.commit()
        return True

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
        batch_position: int | None = None,
        data: bytes,
        batch_id: int | None = None,
        reference_category: ReferenceCategory | None = None,
        task_id: int | None = None,
        worker_id: str | None = None,
    ) -> int | None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
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
            if role == "generated" and batch_id is not None and batch_position is not None:
                unavailable = await (await connection.execute(
                    """
                    SELECT 1 FROM generation_batch_deleted_slots
                    WHERE batch_id = ? AND position = ?
                    UNION ALL
                    SELECT 1 FROM generation_batch_cancelled_slots
                    WHERE batch_id = ? AND position = ?
                    LIMIT 1
                    """,
                    (batch_id, batch_position, batch_id, batch_position),
                )).fetchone()
                if unavailable is not None:
                    await connection.rollback()
                    return None
            if task_id is None:
                cursor = await connection.execute(
                    """
                    INSERT INTO history_images
                        (history_id, batch_id, role, reference_category, mime_type, filename,
                         position, batch_position, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        history_id, batch_id, role, category, mime_type, filename,
                        position, batch_position, data,
                    ),
                )
            else:
                if not worker_id:
                    raise ValueError("worker_id is required when storing a generation task image")
                cursor = await connection.execute(
                    """
                    INSERT INTO history_images
                        (history_id, batch_id, role, reference_category, mime_type, filename,
                         position, batch_position, data)
                    SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?
                    WHERE EXISTS (
                        SELECT 1
                        FROM generation_tasks AS task
                        JOIN generation_batches AS batch ON batch.task_id = task.id
                        WHERE task.id = ? AND task.user_id = ? AND task.history_id = ?
                          AND task.status = 'running'
                          AND task.worker_id = ?
                          AND batch.id = ? AND batch.history_id = ? AND batch.status = 'pending'
                    )
                    """,
                    (
                        history_id, batch_id, role, category, mime_type, filename,
                        position, batch_position, data,
                        task_id, user_id, history_id, worker_id, batch_id, history_id,
                    ),
                )
                if cursor.rowcount != 1:
                    await connection.rollback()
                    raise GenerationTaskNotRunnableError(task_id)
            await connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to store history image")
            return cursor.lastrowid

    async def add_reference_images(
        self,
        *,
        user_id: int,
        history_id: int,
        batch_id: int,
        images: list[tuple[str, str | None, bytes, ReferenceCategory | None]],
    ) -> None:
        if not images:
            return
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            try:
                batch = await (await connection.execute(
                    """
                    SELECT batch.id
                    FROM generation_batches AS batch
                    JOIN history ON history.id = batch.history_id
                    WHERE batch.id = ? AND batch.history_id = ? AND history.user_id = ?
                    """,
                    (batch_id, history_id, user_id),
                )).fetchone()
                if batch is None:
                    raise ValueError("Generation batch does not belong to the requested history")
                position_row = await (await connection.execute(
                    """
                    SELECT COALESCE(MAX(position), -1) + 1
                    FROM history_images
                    WHERE history_id = ? AND batch_id = ? AND role = 'reference'
                    """,
                    (history_id, batch_id),
                )).fetchone()
                next_position = int(position_row[0]) if position_row is not None else 0
                await connection.executemany(
                    """
                    INSERT INTO history_images
                        (history_id, batch_id, role, reference_category, mime_type,
                         filename, position, data)
                    VALUES (?, ?, 'reference', ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            history_id,
                            batch_id,
                            category or "person",
                            mime_type,
                            filename,
                            next_position + offset,
                            data,
                        )
                        for offset, (mime_type, filename, data, category) in enumerate(images)
                    ],
                )
                await connection.commit()
            except Exception:
                await connection.rollback()
                raise

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

    async def complete_generation_batch(
        self,
        history_id: int,
        batch_id: int,
        *,
        elapsed_ms: int | None = None,
        task_id: int | None = None,
        user_id: int | None = None,
        worker_id: str | None = None,
        failure_details: str | None = None,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            batch_row = await (await connection.execute(
                """
                SELECT image_count - (
                           SELECT COUNT(*) FROM generation_batch_deleted_slots
                           WHERE batch_id = generation_batches.id
                       ) - (
                           SELECT COUNT(*) FROM generation_batch_cancelled_slots
                           WHERE batch_id = generation_batches.id
                       ) AS active_image_count,
                       (SELECT COUNT(*) FROM history_images
                        WHERE batch_id = generation_batches.id AND role = 'generated') AS generated_count
                FROM generation_batches
                WHERE id = ? AND history_id = ? AND status = 'pending'
                  AND (? IS NULL OR task_id = ?)
                """,
                (batch_id, history_id, task_id, task_id),
            )).fetchone()
            if batch_row is None:
                await connection.rollback()
                return False
            expected_count, generated_count = map(int, batch_row)
            partial = generated_count < expected_count
            error_code = "partial_generation" if partial else None
            error_message = (
                f"本次请求 {expected_count} 张，服务商只返回 {generated_count} 张，"
                f"其余 {expected_count - generated_count} 张生成失败"
                if partial else None
            )
            if error_message and failure_details:
                error_message = f"{error_message}。失败原因：{failure_details}"
            terminal_status = "failed" if partial else "completed"
            if task_id is not None:
                if user_id is None:
                    await connection.rollback()
                    raise ValueError("user_id is required when completing a generation task")
                if not worker_id:
                    await connection.rollback()
                    raise ValueError("worker_id is required when completing a generation task")
                task_cursor = await connection.execute(
                    """
                    UPDATE generation_tasks
                    SET status = ?, completed_at = CURRENT_TIMESTAMP,
                        error_code = ?, error_message = ?
                    WHERE id = ? AND user_id = ? AND history_id = ? AND status = 'running'
                      AND worker_id = ?
                      AND EXISTS (
                          SELECT 1 FROM generation_batches
                          WHERE id = ? AND history_id = ? AND task_id = generation_tasks.id
                            AND status = 'pending'
                      )
                    """,
                    (
                        terminal_status, error_code, error_message,
                        task_id, user_id, history_id, worker_id, batch_id, history_id,
                    ),
                )
                if task_cursor.rowcount != 1:
                    await connection.rollback()
                    return False
            batch_cursor = await connection.execute(
                """
                UPDATE generation_batches
                SET status = ?, elapsed_ms = ?, generated_count = ?,
                    completed_at = CURRENT_TIMESTAMP,
                    error_code = ?, error_message = ?
                WHERE id = ? AND history_id = ? AND status = 'pending'
                  AND (? IS NULL OR task_id = ?)
                """,
                (
                    terminal_status, elapsed_ms, generated_count, error_code, error_message,
                    batch_id, history_id, task_id, task_id,
                ),
            )
            if batch_cursor.rowcount != 1:
                await connection.rollback()
                return False
            await self._refresh_generation_history_status(connection, history_id)
            await connection.commit()
        return True

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

    async def fail_generation_batch(
        self,
        history_id: int,
        batch_id: int,
        *,
        error_code: str,
        error_message: str,
        task_id: int | None = None,
        user_id: int | None = None,
        worker_id: str | None = None,
        task_status: str = "failed",
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            if task_id is not None:
                if user_id is None:
                    await connection.rollback()
                    raise ValueError("user_id is required when failing a generation task")
                if not worker_id:
                    await connection.rollback()
                    raise ValueError("worker_id is required when failing a generation task")
                task_cursor = await connection.execute(
                    """
                    UPDATE generation_tasks
                    SET status = ?, error_code = ?, error_message = ?,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ? AND history_id = ? AND status = 'running'
                      AND worker_id = ?
                    """,
                    (
                        task_status, error_code, error_message, task_id, user_id,
                        history_id, worker_id,
                    ),
                )
                if task_cursor.rowcount != 1:
                    await connection.rollback()
                    return False
            batch_cursor = await connection.execute(
                """
                UPDATE generation_batches
                SET status = 'failed', error_code = ?, error_message = ?,
                    generated_count = (
                        SELECT COUNT(*) FROM history_images
                        WHERE batch_id = ? AND role = 'generated'
                    ),
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND history_id = ? AND status = 'pending'
                  AND (? IS NULL OR task_id = ?)
                """,
                (error_code, error_message, batch_id, batch_id, history_id, task_id, task_id),
            )
            if batch_cursor.rowcount != 1:
                await connection.rollback()
                return False
            await self._refresh_generation_history_status(connection, history_id)
            await connection.commit()
        return True

    async def fail_stale_generation_tasks(
        self,
        *,
        stale_after_seconds: int = 120,
        include_queued: bool = False,
        error_code: str = "generation_interrupted",
        error_message: str = "生成任务执行中断，请重新生成",
    ) -> int:
        interval = f"-{max(1, stale_after_seconds)} seconds"
        reap_queued = int(include_queued)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            await connection.execute(
                """
                UPDATE generation_batches
                SET status = 'failed', error_code = ?, error_message = ?,
                    generated_count = (
                        SELECT COUNT(*) FROM history_images
                        WHERE batch_id = generation_batches.id AND role = 'generated'
                    ),
                    completed_at = CURRENT_TIMESTAMP
                WHERE status = 'pending'
                  AND EXISTS (
                    SELECT 1 FROM history
                    WHERE history.id = generation_batches.history_id
                      AND history.kind = 'generate' AND history.status = 'pending'
                  )
                  AND (
                    EXISTS (
                      SELECT 1 FROM generation_tasks AS task
                      WHERE task.id = generation_batches.task_id
                        AND task.status IN ('queued', 'running')
                        AND (
                          (task.status = 'running' AND (
                            (task.heartbeat_at IS NOT NULL AND task.heartbeat_at < datetime('now', ?))
                            OR (task.heartbeat_at IS NULL AND task.created_at < datetime('now', ?))
                          ))
                          OR (? = 1 AND task.status = 'queued')
                        )
                    )
                    OR (
                      task_id IS NULL AND created_at < datetime('now', ?)
                      )
                  )
                """,
                (error_code, error_message, interval, interval, reap_queued, interval),
            )
            task_cursor = await connection.execute(
                """
                UPDATE generation_tasks
                SET status = 'failed', error_code = ?, error_message = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE status IN ('queued', 'running')
                  AND (
                    (status = 'running' AND (
                      (heartbeat_at IS NOT NULL AND heartbeat_at < datetime('now', ?))
                      OR (heartbeat_at IS NULL AND created_at < datetime('now', ?))
                    ))
                    OR (? = 1 AND status = 'queued')
                  )
                """,
                (error_code, error_message, interval, interval, reap_queued),
            )
            await connection.execute(
                """
                UPDATE history
                SET status = (
                        SELECT status FROM generation_batches
                        WHERE history_id = history.id
                        ORDER BY id DESC LIMIT 1
                    ),
                    elapsed_ms = (
                        SELECT elapsed_ms FROM generation_batches
                        WHERE history_id = history.id
                        ORDER BY id DESC LIMIT 1
                    ),
                    error_code = (
                        SELECT error_code FROM generation_batches
                        WHERE history_id = history.id
                        ORDER BY id DESC LIMIT 1
                    ),
                    error_message = (
                        SELECT error_message FROM generation_batches
                        WHERE history_id = history.id
                        ORDER BY id DESC LIMIT 1
                    ),
                    completed_at = (
                        SELECT completed_at FROM generation_batches
                        WHERE history_id = history.id
                        ORDER BY id DESC LIMIT 1
                    )
                WHERE status = 'pending'
                  AND EXISTS (
                      SELECT 1 FROM generation_batches
                      WHERE generation_batches.history_id = history.id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM generation_batches
                    WHERE generation_batches.history_id = history.id
                      AND generation_batches.status = 'pending'
                  )
                """,
            )
            await connection.commit()
        return task_cursor.rowcount

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
                SELECT image.id, image.batch_id, image.role, image.mime_type, image.filename,
                       image.position, image.batch_position, image.reference_category
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

            batch_cursor = await connection.execute(
                """
                SELECT batch.id, batch.status, batch.image_count, batch.elapsed_ms,
                       batch.error_code, batch.error_message,
                       COALESCE(batch.generated_count, COUNT(image.id)) AS generated_count,
                       batch.created_at, batch.views_json
                FROM generation_batches AS batch
                LEFT JOIN history_images AS image
                  ON image.batch_id = batch.id AND image.role = 'generated'
                WHERE batch.history_id = ?
                GROUP BY batch.id
                ORDER BY batch.id
                """,
                (history_id,),
            )
            batch_rows = await batch_cursor.fetchall()
            deleted_rows = await (await connection.execute(
                """
                SELECT deleted.batch_id, deleted.position
                FROM generation_batch_deleted_slots AS deleted
                JOIN generation_batches AS batch ON batch.id = deleted.batch_id
                WHERE batch.history_id = ?
                ORDER BY deleted.batch_id, deleted.position
                """,
                (history_id,),
            )).fetchall()
            cancelled_rows = await (await connection.execute(
                """
                SELECT cancelled.batch_id, cancelled.position
                FROM generation_batch_cancelled_slots AS cancelled
                JOIN generation_batches AS batch ON batch.id = cancelled.batch_id
                WHERE batch.history_id = ?
                ORDER BY cancelled.batch_id, cancelled.position
                """,
                (history_id,),
            )).fetchall()

        images = [
            HistoryImageMeta(
                **dict(image_row),
                url=f"/api/history/{history_id}/images/{image_row['id']}",
            )
            for image_row in image_rows
        ]
        deleted_by_batch: dict[int, list[int]] = {}
        for deleted_batch_id, deleted_position in deleted_rows:
            deleted_by_batch.setdefault(int(deleted_batch_id), []).append(int(deleted_position))
        cancelled_by_batch: dict[int, list[int]] = {}
        for cancelled_batch_id, cancelled_position in cancelled_rows:
            cancelled_by_batch.setdefault(int(cancelled_batch_id), []).append(int(cancelled_position))
        batches = []
        for batch_row in batch_rows:
            batch_values = dict(batch_row)
            views = _decode_generation_views(batch_values.pop("views_json", None))
            batches.append(GenerationBatchSummary.model_validate({
                **batch_values,
                "views": views,
                "deleted_positions": deleted_by_batch.get(int(batch_row["id"]), []),
                "cancelled_positions": cancelled_by_batch.get(int(batch_row["id"]), []),
            }))
        return HistoryDetail.model_validate({**dict(row), "images": images, "batches": batches})

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
                SELECT image.batch_id, image.batch_position,
                       config.id AS api_key_config_id, batch.prompt,
                       batch.provider, batch.model, batch.detail, batch.image_count,
                       batch.size, batch.resolution, batch.output_format,
                       batch.background, batch.output_compression, batch.moderation,
                       batch.views_json
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
        batch_position = values.pop("batch_position", None)
        views = _decode_generation_views(values.pop("views_json", None))
        if batch_position is not None and 0 <= int(batch_position) < len(views):
            selected_view = views[int(batch_position)]
            values["prompt"] = selected_view.prompt
            values["image_count"] = 1
            values["view_label"] = selected_view.label
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
            await connection.execute("BEGIN IMMEDIATE")
            image = await (await connection.execute(
                """
                SELECT image.batch_id, image.batch_position
                FROM history_images AS image
                JOIN history ON history.id = image.history_id
                WHERE image.id = ? AND image.history_id = ? AND image.role = 'generated'
                  AND history.user_id = ?
                """,
                (image_id, history_id, user_id),
            )).fetchone()
            if image is None or image[0] is None:
                await connection.rollback()
                return False
            batch_id = int(image[0])
            batch_position = image[1]
            if batch_position is None:
                batch_position_row = await (await connection.execute(
                    """
                    SELECT COUNT(*) FROM history_images AS earlier
                    WHERE earlier.batch_id = ? AND earlier.role = 'generated'
                      AND earlier.id < ?
                    """,
                    (batch_id, image_id),
                )).fetchone()
                batch_position = int(batch_position_row[0])
            await connection.execute(
                """
                INSERT OR IGNORE INTO generation_batch_deleted_slots (batch_id, position)
                VALUES (?, ?)
                """,
                (batch_id, batch_position),
            )
            await connection.execute(
                "DELETE FROM history_images WHERE id = ? AND history_id = ?",
                (image_id, history_id),
            )
            await connection.execute(
                """
                UPDATE generation_batches
                SET generated_count = (
                    SELECT COUNT(*) FROM history_images
                    WHERE batch_id = ? AND role = 'generated'
                )
                WHERE id = ? AND history_id = ?
                """,
                (batch_id, batch_id, history_id),
            )
            await connection.commit()
        return True

    async def generation_slot_is_unavailable(
        self,
        user_id: int,
        history_id: int,
        batch_id: int,
        position: int,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            row = await (await connection.execute(
                """
                SELECT 1
                FROM generation_batches AS batch
                JOIN history ON history.id = batch.history_id
                WHERE batch.id = ? AND batch.history_id = ? AND history.user_id = ?
                  AND (
                    EXISTS (
                        SELECT 1 FROM generation_batch_deleted_slots
                        WHERE batch_id = batch.id AND position = ?
                    )
                    OR EXISTS (
                        SELECT 1 FROM generation_batch_cancelled_slots
                        WHERE batch_id = batch.id AND position = ?
                    )
                  )
                """,
                (batch_id, history_id, user_id, position, position),
            )).fetchone()
        return row is not None

    async def cancel_generation_slot(
        self,
        user_id: int,
        history_id: int,
        batch_id: int,
        position: int,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            batch = await (await connection.execute(
                """
                SELECT batch.image_count
                FROM generation_batches AS batch
                JOIN history ON history.id = batch.history_id
                WHERE batch.id = ? AND batch.history_id = ? AND history.user_id = ?
                  AND batch.status = 'pending'
                  AND NOT EXISTS (
                      SELECT 1 FROM generation_batch_deleted_slots
                      WHERE batch_id = batch.id AND position = ?
                  )
                """,
                (batch_id, history_id, user_id, position),
            )).fetchone()
            if batch is None or position < 0 or position >= int(batch[0]):
                await connection.rollback()
                return False
            await connection.execute(
                """
                INSERT OR IGNORE INTO generation_batch_cancelled_slots (batch_id, position)
                VALUES (?, ?)
                """,
                (batch_id, position),
            )
            await connection.execute(
                """
                DELETE FROM history_images
                WHERE history_id = ? AND batch_id = ? AND role = 'generated'
                  AND batch_position = ?
                """,
                (history_id, batch_id, position),
            )
            await connection.execute(
                """
                UPDATE generation_batches
                SET generated_count = (
                    SELECT COUNT(*) FROM history_images
                    WHERE batch_id = ? AND role = 'generated'
                )
                WHERE id = ? AND history_id = ?
                """,
                (batch_id, batch_id, history_id),
            )
            await connection.commit()
        return True

    async def delete_generation_slot(
        self,
        user_id: int,
        history_id: int,
        batch_id: int,
        position: int,
    ) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            batch = await (await connection.execute(
                """
                SELECT batch.image_count
                FROM generation_batches AS batch
                JOIN history ON history.id = batch.history_id
                WHERE batch.id = ? AND batch.history_id = ? AND history.user_id = ?
                """,
                (batch_id, history_id, user_id),
            )).fetchone()
            if batch is None or position < 0 or position >= int(batch[0]):
                await connection.rollback()
                return False
            await connection.execute(
                """
                INSERT OR IGNORE INTO generation_batch_deleted_slots (batch_id, position)
                VALUES (?, ?)
                """,
                (batch_id, position),
            )
            await connection.execute(
                """
                DELETE FROM generation_batch_cancelled_slots
                WHERE batch_id = ? AND position = ?
                """,
                (batch_id, position),
            )
            await connection.execute(
                """
                DELETE FROM history_images
                WHERE history_id = ? AND batch_id = ? AND role = 'generated'
                  AND batch_position = ?
                """,
                (history_id, batch_id, position),
            )
            await connection.execute(
                """
                UPDATE generation_batches
                SET generated_count = (
                    SELECT COUNT(*) FROM history_images
                    WHERE batch_id = ? AND role = 'generated'
                )
                WHERE id = ? AND history_id = ?
                """,
                (batch_id, batch_id, history_id),
            )
            await connection.commit()
        return True
