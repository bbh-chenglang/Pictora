from pathlib import Path
from uuid import uuid4

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.project import Project, ProjectDeleteResult, ProjectSummary
from app.schemas.history import HistorySummary


class ProjectNotFoundError(Exception):
    pass


class ProjectNameTakenError(Exception):
    pass


class ProjectRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def get_owned(self, project_id: int, user_id: int) -> Project | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                "SELECT id, user_id, name, created_at, updated_at FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            )
            row = await cursor.fetchone()
        return Project.model_validate(dict(row)) if row else None

    async def list_with_history(self, user_id: int) -> list[ProjectSummary]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            projects_cursor = await connection.execute(
                """
                SELECT id, user_id, name, created_at, updated_at
                FROM projects WHERE user_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (user_id,),
            )
            projects = await projects_cursor.fetchall()
            histories_cursor = await connection.execute(
                """
                SELECT id, project_id, kind, status, prompt, provider, model, detail,
                       image_count, size, resolution, elapsed_ms, error_code, error_message, created_at
                FROM history
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (user_id,),
            )
            histories = await histories_cursor.fetchall()
        grouped: dict[int, list[HistorySummary]] = {}
        for row in histories:
            data = dict(row)
            project_id = data.pop("project_id")
            grouped.setdefault(project_id, []).append(HistorySummary.model_validate(data))
        return [
            ProjectSummary(
                **dict(row),
                history=grouped.get(row["id"], []),
                history_count=len(grouped.get(row["id"], [])),
            )
            for row in projects
        ]

    async def create(self, user_id: int, name: str) -> Project:
        normalized = name.strip()
        async with aiosqlite.connect(self.database_path) as connection:
            try:
                cursor = await connection.execute(
                    "INSERT INTO projects (user_id, name) VALUES (?, ?)",
                    (user_id, normalized),
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                raise ProjectNameTakenError(normalized) from exc
            project_id = cursor.lastrowid
        project = await self.get_owned(project_id, user_id)
        if project is None:
            raise RuntimeError("Created project cannot be loaded")
        return project

    async def rename(self, project_id: int, user_id: int, name: str) -> Project:
        normalized = name.strip()
        async with aiosqlite.connect(self.database_path) as connection:
            try:
                cursor = await connection.execute(
                    """
                    UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                    """,
                    (normalized, project_id, user_id),
                )
                if cursor.rowcount == 0:
                    raise ProjectNotFoundError(project_id)
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                raise ProjectNameTakenError(normalized) from exc
        project = await self.get_owned(project_id, user_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    async def rename_if_empty(self, project_id: int, user_id: int, name: str) -> bool:
        normalized = name.strip()
        if not normalized:
            return False
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ? AND trim(name) IN ('', '第一个项目')
                """,
                (normalized[:80], project_id, user_id),
            )
            await connection.commit()
        return cursor.rowcount > 0

    async def delete_with_generation_tasks(
        self,
        project_id: int,
        user_id: int,
    ) -> tuple[ProjectDeleteResult, list[int]]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            cursor = await connection.execute(
                "SELECT id, name FROM projects WHERE id = ? AND user_id = ?",
                (project_id, user_id),
            )
            project = await cursor.fetchone()
            if project is None:
                await connection.rollback()
                raise ProjectNotFoundError(project_id)
            count_cursor = await connection.execute(
                "SELECT COUNT(*) FROM projects WHERE user_id = ?", (user_id,)
            )
            project_count = (await count_cursor.fetchone())[0]
            history_cursor = await connection.execute(
                "SELECT COUNT(*) FROM history WHERE project_id = ? AND user_id = ?",
                (project_id, user_id),
            )
            deleted_count = (await history_cursor.fetchone())[0]
            task_rows = await (await connection.execute(
                """
                SELECT task.id
                FROM generation_tasks AS task
                JOIN history ON history.id = task.history_id
                WHERE task.user_id = ? AND history.project_id = ?
                  AND task.status IN ('queued', 'running')
                ORDER BY task.id
                """,
                (user_id, project_id),
            )).fetchall()
            task_ids = [int(row[0]) for row in task_rows]
            if project_count == 1:
                temporary_name = f"第一个项目（临时-{uuid4().hex}）"
                await connection.execute(
                    "INSERT INTO projects (user_id, name) VALUES (?, ?)",
                    (user_id, temporary_name),
                )
            await connection.execute(
                "DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
            )
            if project_count == 1:
                await connection.execute(
                    "UPDATE projects SET name = '第一个项目', updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND name = ?",
                    (user_id, temporary_name),
                )
            await connection.commit()
        summaries = await self.list_with_history(user_id)
        return (
            ProjectDeleteResult(
                deleted_history_count=deleted_count,
                selected_project_id=summaries[0].id,
                projects=summaries,
            ),
            task_ids,
        )

    async def delete(self, project_id: int, user_id: int) -> ProjectDeleteResult:
        result, _ = await self.delete_with_generation_tasks(project_id, user_id)
        return result

    async def delete_history_with_generation_tasks(
        self,
        project_id: int,
        user_id: int,
        history_ids: list[int],
    ) -> tuple[int, list[int]]:
        ids = sorted(set(history_ids))
        if not ids:
            return 0, []
        placeholders = ",".join("?" for _ in ids)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            await connection.execute("BEGIN IMMEDIATE")
            project_cursor = await connection.execute(
                "SELECT 1 FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id)
            )
            if await project_cursor.fetchone() is None:
                await connection.rollback()
                raise ProjectNotFoundError(project_id)
            task_rows = await (await connection.execute(
                f"""
                SELECT task.id
                FROM generation_tasks AS task
                JOIN history ON history.id = task.history_id
                WHERE task.user_id = ? AND history.project_id = ?
                  AND history.id IN ({placeholders})
                  AND task.status IN ('queued', 'running')
                ORDER BY task.id
                """,
                (user_id, project_id, *ids),
            )).fetchall()
            task_ids = [int(row[0]) for row in task_rows]
            cursor = await connection.execute(
                f"DELETE FROM history WHERE user_id = ? AND project_id = ? AND id IN ({placeholders})",
                (user_id, project_id, *ids),
            )
            await connection.commit()
        return cursor.rowcount, task_ids

    async def delete_history(self, project_id: int, user_id: int, history_ids: list[int]) -> int:
        deleted_count, _ = await self.delete_history_with_generation_tasks(
            project_id,
            user_id,
            history_ids,
        )
        return deleted_count
