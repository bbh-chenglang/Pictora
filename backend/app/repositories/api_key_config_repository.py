from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH
from app.schemas.api_key_config import StoredApiKeyConfig


class ApiKeyConfigNotFoundError(Exception):
    pass


class ApiKeyConfigAliasTakenError(Exception):
    pass


class ApiKeyConfigRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def list_for_user(self, user_id: int) -> list[StoredApiKeyConfig]:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, user_id, alias, api_key, provider_type, model, created_at, updated_at
                FROM api_key_configs
                WHERE user_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
        return [StoredApiKeyConfig(**dict(row)) for row in rows]

    async def get_owned(self, user_id: int, config_id: int) -> StoredApiKeyConfig | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT id, user_id, alias, api_key, provider_type, model, created_at, updated_at
                FROM api_key_configs WHERE id = ? AND user_id = ?
                """,
                (config_id, user_id),
            )
            row = await cursor.fetchone()
        return StoredApiKeyConfig(**dict(row)) if row else None

    async def create(
        self,
        user_id: int,
        alias: str,
        api_key: str,
        provider_type: str,
        model: str,
    ) -> StoredApiKeyConfig:
        normalized_alias = alias.strip()
        async with aiosqlite.connect(self.database_path) as connection:
            try:
                cursor = await connection.execute(
                    """
                    INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, normalized_alias, api_key, provider_type, model.strip()),
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                raise ApiKeyConfigAliasTakenError(normalized_alias) from exc
        config = await self.get_owned(user_id, cursor.lastrowid)
        if config is None:
            raise RuntimeError("Created API key config cannot be loaded")
        return config

    async def delete(self, user_id: int, config_id: int) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM api_key_configs WHERE user_id = ?", (user_id,)
            )
            count = (await cursor.fetchone())[0]
            if count <= 1:
                raise ValueError("Cannot delete the last API key config")
            cursor = await connection.execute(
                "DELETE FROM api_key_configs WHERE id = ? AND user_id = ?",
                (config_id, user_id),
            )
            if cursor.rowcount == 0:
                raise ApiKeyConfigNotFoundError(config_id)
            await connection.commit()
