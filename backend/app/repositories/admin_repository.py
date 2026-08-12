from pathlib import Path
import sqlite3

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.admin import AdminUsageRecord, AdminUserSummary


class AdminRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def list_users(
        self, *, search: str = "", page: int = 1, page_size: int = 20
    ) -> tuple[list[AdminUserSummary], int, int, int, int]:
        normalized_search = search.strip().casefold()
        where = "WHERE u.email IS NOT NULL"
        parameters: list[object] = []
        if normalized_search:
            where += " AND (lower(u.username) LIKE ? OR lower(u.email) LIKE ?)"
            pattern = f"%{normalized_search}%"
            parameters.extend([pattern, pattern])
        offset = (page - 1) * page_size
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(
                f"""
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
                {where}
                GROUP BY u.id
                ORDER BY COALESCE(u.last_activity_at, u.created_at) DESC, u.id DESC
                LIMIT ? OFFSET ?
                """,
                (*parameters, page_size, offset),
            )).fetchall()
            result_total = await (await connection.execute(
                f"""
                SELECT COUNT(*)
                FROM users AS u
                {where}
                """,
                parameters,
            )).fetchone()
            totals = await (await connection.execute(
                """
                SELECT COUNT(*), SUM(CASE WHEN is_admin = 1 THEN 1 ELSE 0 END)
                FROM users WHERE email IS NOT NULL
                """
            )).fetchone()
            usage_total = await (await connection.execute(
                """
                SELECT COUNT(*)
                FROM history AS h
                JOIN users AS u ON u.id = h.user_id
                WHERE u.email IS NOT NULL
                """
            )).fetchone()
        return (
            [self._summary(row) for row in rows],
            int(totals[0] or 0),
            int(result_total[0] or 0),
            int(totals[1] or 0),
            int(usage_total[0] or 0),
        )

    async def get_user(self, user_id: int) -> AdminUserSummary | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            row = await (await connection.execute(
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
                WHERE u.id = ? AND u.email IS NOT NULL
                GROUP BY u.id
                """,
                (user_id,),
            )).fetchone()
        return self._summary(row) if row is not None else None

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
