from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from app.database import DATABASE_PATH


@dataclass(frozen=True)
class StoredProviderSettings:
    provider_name: str
    base_url: str
    model: str
    api_key: str


class SettingsRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def get(self) -> StoredProviderSettings:
        async with aiosqlite.connect(self.database_path) as connection:
            connection.row_factory = aiosqlite.Row
            cursor = await connection.execute(
                """
                SELECT provider_name, base_url, model, api_key
                FROM settings
                WHERE id = 1
                """
            )
            row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("Provider settings are not initialized")
        return StoredProviderSettings(**dict(row))

    async def update(
        self,
        model: str,
        api_key: str | None,
    ) -> StoredProviderSettings:
        async with aiosqlite.connect(self.database_path) as connection:
            if api_key is None:
                await connection.execute(
                    """
                    UPDATE settings
                    SET model = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """,
                    (model,),
                )
            else:
                await connection.execute(
                    """
                    UPDATE settings
                    SET model = ?, api_key = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                    """,
                    (model, api_key),
                )
            await connection.commit()
        return await self.get()
