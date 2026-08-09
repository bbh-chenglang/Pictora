from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from app.auth import SESSION_MAX_AGE
from app.database import DATABASE_PATH, FIXED_BASE_URL, FIXED_PROVIDER_NAME
from app.schemas.auth import StoredSessionUser, StoredUser
from app.repositories.settings_repository import StoredProviderSettings


class UserAlreadyExistsError(Exception):
    pass


class UserRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def create(self, username: str, password_hash: str) -> StoredUser:
        async with aiosqlite.connect(self.database_path) as connection:
            try:
                cursor = await connection.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash),
                )
                await connection.execute(
                    """
                    INSERT INTO api_key_configs (user_id, alias, api_key, provider_type, model)
                    VALUES (?, '默认配置', '', 'gpt', 'gpt-image-1.5')
                    """,
                    (cursor.lastrowid,),
                )
                await connection.execute(
                    "UPDATE users SET active_api_key_config_id = last_insert_rowid() WHERE id = ?",
                    (cursor.lastrowid,),
                )
                await connection.commit()
            except aiosqlite.IntegrityError as exc:
                raise UserAlreadyExistsError(username) from exc
            if cursor.lastrowid is None:
                raise RuntimeError("Failed to create user")
        user = await self.get_by_id(cursor.lastrowid)
        if user is None:
            raise RuntimeError("Created user cannot be loaded")
        return user

    async def get_by_id(self, user_id: int) -> StoredUser | None:
        return await self._get_user("id = ?", (user_id,))

    async def get_by_username(self, username: str) -> StoredUser | None:
        return await self._get_user("username = ?", (username,))

    async def _get_user(self, predicate: str, parameters: tuple[object, ...]) -> StoredUser | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                f"SELECT id, username, password_hash, api_key, model, created_at, updated_at FROM users WHERE {predicate}",
                parameters,
            )
            row = await cursor.fetchone()
        return StoredUser.model_validate(dict(row)) if row else None

    async def get_session_user(self, token_hash: str) -> StoredSessionUser | None:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT u.id, u.username, u.api_key, u.model
                FROM user_sessions AS s
                JOIN users AS u ON u.id = s.user_id
                WHERE s.token_hash = ? AND s.expires_at > ?
                """,
                (token_hash, datetime.now(timezone.utc).isoformat()),
            )
            row = await cursor.fetchone()
        return StoredSessionUser.model_validate(dict(row)) if row else None

    async def create_session(self, user_id: int, token_hash: str) -> datetime:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                "INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user_id, token_hash, expires_at.isoformat()),
            )
            await connection.commit()
        return expires_at

    async def delete_session(self, token_hash: str) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_hash,))
            await connection.commit()

    async def delete_sessions_for_user(self, user_id: int) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
            await connection.commit()

    async def update_password(self, user_id: int, password_hash: str) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (password_hash, user_id),
            )
            await connection.commit()

    async def get_settings(self, user_id: int) -> StoredProviderSettings:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                "SELECT ? AS provider_name, ? AS base_url, model, api_key FROM users WHERE id = ?",
                (FIXED_PROVIDER_NAME, FIXED_BASE_URL, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("User settings are not initialized")
        return StoredProviderSettings(**dict(row))

    async def update_settings(self, user_id: int, model: str, api_key: str | None) -> StoredProviderSettings:
        async with aiosqlite.connect(self.database_path) as connection:
            if api_key is None:
                await connection.execute(
                    "UPDATE users SET model = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (model, user_id),
                )
            else:
                await connection.execute(
                    "UPDATE users SET model = ?, api_key = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (model, api_key, user_id),
                )
            await connection.commit()
        return await self.get_settings(user_id)
