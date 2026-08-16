import json
from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.skill import SkillCreateRequest, SkillSummary


class SkillNotFoundError(Exception):
    pass


class SkillStateError(Exception):
    pass


class SkillRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    @staticmethod
    def _summary(row: aiosqlite.Row) -> SkillSummary:
        data = dict(row)
        data["workflow"] = json.loads(data.pop("workflow_json"))
        data["has_cover"] = bool(data["has_cover"])
        data["is_favorited"] = bool(data["is_favorited"])
        return SkillSummary.model_validate(data)

    async def list(
        self,
        *,
        user_id: int,
        scope: str,
        search: str = "",
        category: str = "",
    ) -> list[SkillSummary]:
        conditions: list[str] = []
        parameters: list[object] = [user_id]
        if scope == "mine":
            conditions.append("s.user_id = ?")
            parameters.append(user_id)
        elif scope == "favorites":
            conditions.extend([
                "s.status = 'published'",
                "EXISTS (SELECT 1 FROM skill_favorites own_favorite WHERE own_favorite.skill_id = s.id AND own_favorite.user_id = ?)",
            ])
            parameters.append(user_id)
        elif scope == "review":
            conditions.append("s.status = 'pending'")
        else:
            conditions.append("s.status = 'published'")
        if search.strip():
            conditions.append("(lower(s.title) LIKE ? OR lower(s.description) LIKE ? OR lower(u.username) LIKE ?)")
            pattern = f"%{search.strip().casefold()}%"
            parameters.extend([pattern, pattern, pattern])
        if category:
            conditions.append("s.category = ?")
            parameters.append(category)
        where = " AND ".join(conditions) or "1 = 1"
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(
                f"""
                SELECT s.id, s.user_id AS author_id, u.username AS author_name,
                       s.title, s.description, s.category, s.status, s.workflow_json,
                       (s.cover_data IS NOT NULL) AS has_cover,
                       EXISTS (SELECT 1 FROM skill_favorites f WHERE f.skill_id = s.id AND f.user_id = ?) AS is_favorited,
                       (SELECT COUNT(*) FROM skill_favorites f WHERE f.skill_id = s.id) AS favorite_count,
                       (SELECT COUNT(*) FROM skill_uses su WHERE su.skill_id = s.id) AS use_count,
                       s.moderation_note, s.created_at, s.updated_at, s.published_at
                FROM skills s
                JOIN users u ON u.id = s.user_id
                WHERE {where}
                ORDER BY CASE s.status WHEN 'pending' THEN 0 WHEN 'published' THEN 1 ELSE 2 END,
                         COALESCE(s.published_at, s.updated_at) DESC, s.id DESC
                LIMIT 200
                """,
                parameters,
            )).fetchall()
        return [self._summary(row) for row in rows]

    async def get(
        self, skill_id: int, *, user_id: int, is_admin: bool = False
    ) -> SkillSummary:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            row = await (await connection.execute(
                """
                SELECT s.id, s.user_id AS author_id, u.username AS author_name,
                       s.title, s.description, s.category, s.status, s.workflow_json,
                       (s.cover_data IS NOT NULL) AS has_cover,
                       EXISTS (SELECT 1 FROM skill_favorites f WHERE f.skill_id = s.id AND f.user_id = ?) AS is_favorited,
                       (SELECT COUNT(*) FROM skill_favorites f WHERE f.skill_id = s.id) AS favorite_count,
                       (SELECT COUNT(*) FROM skill_uses su WHERE su.skill_id = s.id) AS use_count,
                       s.moderation_note, s.created_at, s.updated_at, s.published_at
                FROM skills s JOIN users u ON u.id = s.user_id
                WHERE s.id = ?
                """,
                (user_id, skill_id),
            )).fetchone()
        if row is None or not (row["status"] == "published" or row["author_id"] == user_id or is_admin):
            raise SkillNotFoundError(skill_id)
        return self._summary(row)

    async def create(
        self,
        *,
        user_id: int,
        request: SkillCreateRequest,
        cover_mime_type: str | None,
        cover_data: bytes | None,
    ) -> SkillSummary:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                INSERT INTO skills (
                    user_id, title, description, category, workflow_json,
                    cover_mime_type, cover_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    request.title,
                    request.description,
                    request.category,
                    request.workflow.model_dump_json(),
                    cover_mime_type,
                    cover_data,
                ),
            )
            await connection.commit()
            skill_id = int(cursor.lastrowid or 0)
        return await self.get(skill_id, user_id=user_id)

    async def submit(self, skill_id: int, *, user_id: int) -> SkillSummary:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                UPDATE skills
                SET status = 'pending', moderation_note = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ? AND status IN ('draft', 'rejected')
                """,
                (skill_id, user_id),
            )
            await connection.commit()
        if cursor.rowcount == 0:
            raise SkillStateError("只有草稿或被拒绝的技能可以提交审核")
        return await self.get(skill_id, user_id=user_id)

    async def review(
        self, skill_id: int, *, decision: str, note: str, admin_id: int
    ) -> SkillSummary:
        del admin_id
        published = "CURRENT_TIMESTAMP" if decision == "published" else "NULL"
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                f"""
                UPDATE skills
                SET status = ?, moderation_note = ?, published_at = {published},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending'
                """,
                (decision, note or None, skill_id),
            )
            await connection.commit()
        if cursor.rowcount == 0:
            raise SkillStateError("只有待审核技能可以处理")
        return await self.get(skill_id, user_id=0, is_admin=True)

    async def set_favorite(self, skill_id: int, *, user_id: int, favorite: bool) -> SkillSummary:
        await self.get(skill_id, user_id=user_id)
        async with aiosqlite.connect(self.database_path) as connection:
            if favorite:
                await connection.execute(
                    "INSERT OR IGNORE INTO skill_favorites (skill_id, user_id) VALUES (?, ?)",
                    (skill_id, user_id),
                )
            else:
                await connection.execute(
                    "DELETE FROM skill_favorites WHERE skill_id = ? AND user_id = ?",
                    (skill_id, user_id),
                )
            await connection.commit()
        return await self.get(skill_id, user_id=user_id)

    async def record_use(self, skill_id: int, *, user_id: int) -> SkillSummary:
        skill = await self.get(skill_id, user_id=user_id)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                "INSERT INTO skill_uses (skill_id, user_id) VALUES (?, ?)",
                (skill_id, user_id),
            )
            await connection.commit()
        return await self.get(skill.id, user_id=user_id)

    async def delete(self, skill_id: int, *, user_id: int, is_admin: bool = False) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("PRAGMA foreign_keys = ON")
            if is_admin:
                cursor = await connection.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            else:
                cursor = await connection.execute(
                    "DELETE FROM skills WHERE id = ? AND user_id = ? AND status IN ('draft', 'rejected')",
                    (skill_id, user_id),
                )
            await connection.commit()
        if cursor.rowcount == 0:
            raise SkillStateError("只能删除自己的草稿或被拒绝的技能")

    async def cover(self, skill_id: int, *, user_id: int, is_admin: bool = False) -> tuple[str, bytes]:
        await self.get(skill_id, user_id=user_id, is_admin=is_admin)
        async with aiosqlite.connect(self.database_path) as connection:
            row = await (await connection.execute(
                "SELECT cover_mime_type, cover_data FROM skills WHERE id = ?", (skill_id,)
            )).fetchone()
        if row is None or row[1] is None:
            raise SkillNotFoundError(skill_id)
        return str(row[0]), bytes(row[1])
