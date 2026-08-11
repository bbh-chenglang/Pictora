from pathlib import Path
import sqlite3

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.admin import AdminUsageRecord, AdminUserSummary


class AdminRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def list_users(self) -> list[AdminUserSummary]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(
                """
                SELECT
                    u.id, u.username, u.email, u.is_admin, u.created_at,
                    u.last_login_at, u.last_activity_at,
                    MAX(h.created_at) AS last_used_at,
                    COUNT(h.id) AS usage_count,
                    SUM(CASE WHEN h.kind = 'generate' THEN 1 ELSE 0 END) AS generation_count,
                    SUM(CASE WHEN h.kind = 'analyze' THEN 1 ELSE 0 END) AS analysis_count,
                    COALESCE(SUM(h.elapsed_ms), 0) AS total_elapsed_ms,
                    GROUP_CONCAT(DISTINCT h.model) AS models_used
                FROM users AS u
                LEFT JOIN history AS h ON h.user_id = u.id
                WHERE u.email IS NOT NULL
                GROUP BY u.id
                ORDER BY COALESCE(u.last_activity_at, u.created_at) DESC, u.id DESC
                """
            )).fetchall()
        return [self._summary(row) for row in rows]

    async def get_user(self, user_id: int) -> AdminUserSummary | None:
        users = await self.list_users()
        return next((user for user in users if user.id == user_id), None)

    async def list_usage(self, user_id: int, limit: int = 100) -> list[AdminUsageRecord]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(
                """
                SELECT id, kind, status, provider, model, detail, image_count,
                       size, resolution, elapsed_ms, created_at, completed_at
                FROM history
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )).fetchall()
        return [AdminUsageRecord.model_validate(dict(row)) for row in rows]

    @staticmethod
    def _summary(row: sqlite3.Row) -> AdminUserSummary:
        values = dict(row)
        values["models_used"] = [
            model for model in str(values.get("models_used") or "").split(",") if model
        ]
        return AdminUserSummary.model_validate(values)
