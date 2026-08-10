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

    async def update(
        self,
        user_id: int,
        config_id: int,
        *,
        alias: str | None = None,
        api_key: str | None = None,
        provider_type: str | None = None,
        model: str | None = None,
    ) -> StoredApiKeyConfig:
        current = await self.get_owned(user_id, config_id)
        if current is None:
            raise ApiKeyConfigNotFoundError(config_id)
        values = (
            alias.strip() if alias is not None else current.alias,
            current.api_key if api_key is None or not api_key.strip() else api_key.strip(),
            provider_type or current.provider_type,
            model.strip() if model is not None else current.model,
        )
        async with aiosqlite.connect(self.database_path) as connection:
            try:
                await connection.execute(
                    """
                    UPDATE api_key_configs
                    SET alias = ?, api_key = ?, provider_type = ?, model = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ?
                    """,
                    (*values, config_id, user_id),
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                raise ApiKeyConfigAliasTakenError(values[0]) from exc
        updated = await self.get_owned(user_id, config_id)
        if updated is None:
            raise ApiKeyConfigNotFoundError(config_id)
        return updated

    async def get_active_id(self, user_id: int) -> int | None:
        async with aiosqlite.connect(self.database_path) as connection:
            row = await (await connection.execute(
                "SELECT active_api_key_config_id FROM users WHERE id = ?", (user_id,)
            )).fetchone()
        return row[0] if row and row[0] is not None else None

    async def set_active(self, user_id: int, config_id: int) -> StoredApiKeyConfig:
        config = await self.get_owned(user_id, config_id)
        if config is None:
            raise ApiKeyConfigNotFoundError(config_id)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                "UPDATE users SET active_api_key_config_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (config_id, user_id),
            )
            await connection.commit()
        return config

    async def delete(self, user_id: int, config_id: int) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            cursor = await connection.execute(
                "DELETE FROM api_key_configs WHERE id = ? AND user_id = ?",
                (config_id, user_id),
            )
            if cursor.rowcount == 0:
                raise ApiKeyConfigNotFoundError(config_id)
            fallback = await (await connection.execute(
                """
                SELECT id FROM api_key_configs
                WHERE user_id = ?
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (user_id,),
            )).fetchone()
            await connection.execute(
                """
                UPDATE users
                SET active_api_key_config_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND active_api_key_config_id = ?
                """,
                (fallback[0] if fallback else None, user_id, config_id),
            )
            await connection.commit()
