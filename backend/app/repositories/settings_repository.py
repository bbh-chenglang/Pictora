from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH, FIXED_BASE_URL, FIXED_PROVIDER_NAME


@dataclass(frozen=True)
class StoredProviderSettings:
    provider_name: str
    base_url: str
    model: str
    api_key: str


class SettingsRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def get(self, user_id: int) -> StoredProviderSettings:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                "SELECT ? AS provider_name, ? AS base_url, model, api_key FROM users WHERE id = ?",
                (FIXED_PROVIDER_NAME, FIXED_BASE_URL, user_id),
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Provider settings are not initialized")
        return StoredProviderSettings(**dict(row))

    async def update(
        self,
        user_id: int,
        model: str,
        api_key: str | None,
    ) -> StoredProviderSettings:
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
        return await self.get(user_id)
