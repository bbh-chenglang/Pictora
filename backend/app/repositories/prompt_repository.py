from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.prompt import PromptCreateRequest, PromptSummary


class PromptNotFoundError(Exception):
    pass


class PromptRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    @staticmethod
    def _summary(row: aiosqlite.Row) -> PromptSummary:
        return PromptSummary.model_validate(dict(row))

    async def list(self, *, user_id: int, search: str = "", category: str = "") -> list[PromptSummary]:
        conditions = ["user_id = ?"]
        parameters: list[object] = [user_id]
        normalized_search = search.strip()
        if normalized_search:
            conditions.append("(lower(name) LIKE ? OR lower(prompt) LIKE ?)")
            pattern = f"%{normalized_search.casefold()}%"
            parameters.extend([pattern, pattern])
        if category:
            conditions.append("category = ?")
            parameters.append(category)
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            rows = await (await connection.execute(
                f"""
                SELECT id, user_id, name, prompt, category, created_at, updated_at
                FROM prompt_entries
                WHERE {' AND '.join(conditions)}
                ORDER BY updated_at DESC, id DESC
                LIMIT 200
                """,
                parameters,
            )).fetchall()
        return [self._summary(row) for row in rows]

    async def get(self, prompt_id: int, *, user_id: int) -> PromptSummary:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            row = await (await connection.execute(
                """
                SELECT id, user_id, name, prompt, category, created_at, updated_at
                FROM prompt_entries WHERE id = ? AND user_id = ?
                """,
                (prompt_id, user_id),
            )).fetchone()
        if row is None:
            raise PromptNotFoundError(prompt_id)
        return self._summary(row)

    async def create(self, user_id: int, request: PromptCreateRequest) -> PromptSummary:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                "INSERT INTO prompt_entries (user_id, name, prompt, category) VALUES (?, ?, ?, ?)",
                (user_id, request.name, request.prompt, request.category),
            )
            await connection.commit()
            prompt_id = int(cursor.lastrowid or 0)
        return await self.get(prompt_id, user_id=user_id)

    async def update(self, prompt_id: int, *, user_id: int, request: PromptCreateRequest) -> PromptSummary:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                """
                UPDATE prompt_entries
                SET name = ?, prompt = ?, category = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (request.name, request.prompt, request.category, prompt_id, user_id),
            )
            await connection.commit()
        if cursor.rowcount == 0:
            raise PromptNotFoundError(prompt_id)
        return await self.get(prompt_id, user_id=user_id)

    async def delete(self, prompt_id: int, *, user_id: int) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                "DELETE FROM prompt_entries WHERE id = ? AND user_id = ?",
                (prompt_id, user_id),
            )
            await connection.commit()
        if cursor.rowcount == 0:
            raise PromptNotFoundError(prompt_id)
