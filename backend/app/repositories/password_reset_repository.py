import asyncio
from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path

import aiosqlite

from app.auth import verify_password
from app.database import DATABASE_PATH
from app.repositories.verification_code_repository import VerificationCodeCooldownError


class PasswordResetRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def store(
        self, email: str, user_id: int | None, code_hash: str, *,
        ttl_seconds: int, cooldown_seconds: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            # Retain consumed/failed requests through their cooldown, but do not
            # accumulate records for arbitrary unknown addresses indefinitely.
            await connection.execute(
                "DELETE FROM password_reset_codes WHERE expires_at <= ? AND last_sent_at <= ?",
                (now.isoformat(), (now - timedelta(seconds=cooldown_seconds)).isoformat()),
            )
            row = await (await connection.execute(
                "SELECT last_sent_at FROM password_reset_codes WHERE email = ?", (email,),
            )).fetchone()
            if row is not None:
                remaining = cooldown_seconds - (now - datetime.fromisoformat(row[0])).total_seconds()
                if remaining > 0:
                    raise VerificationCodeCooldownError(max(1, ceil(remaining)))
            await connection.execute(
                """
                INSERT INTO password_reset_codes
                    (email, user_id, code_hash, expires_at, last_sent_at, failed_attempts)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(email) DO UPDATE SET
                    user_id = excluded.user_id, code_hash = excluded.code_hash,
                    expires_at = excluded.expires_at, last_sent_at = excluded.last_sent_at,
                    failed_attempts = 0
                """,
                (email, user_id, code_hash,
                 (now + timedelta(seconds=ttl_seconds)).isoformat(), now.isoformat()),
            )
            await connection.commit()

    async def invalidate(self, email: str, code_hash: str) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            # A late failure from an older email must not invalidate its replacement.
            await connection.execute(
                "UPDATE password_reset_codes SET code_hash = NULL WHERE email = ? AND code_hash = ?",
                (email, code_hash),
            )
            await connection.commit()

    async def reset_password(self, email: str, code: str, password_hash: str) -> bool:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            row = await (await connection.execute(
                """SELECT user_id, code_hash, expires_at, failed_attempts
                   FROM password_reset_codes WHERE email = ?""", (email,),
            )).fetchone()
            if row is None or row[1] is None:
                return False
            if datetime.fromisoformat(row[2]) <= datetime.now(timezone.utc) or row[3] >= 5:
                await connection.execute(
                    "UPDATE password_reset_codes SET code_hash = NULL WHERE email = ?", (email,),
                )
                await connection.commit()
                return False
            matches = await asyncio.to_thread(verify_password, code, row[1])
            if not matches or row[0] is None:
                await connection.execute(
                    """UPDATE password_reset_codes SET failed_attempts = failed_attempts + 1,
                       code_hash = CASE WHEN failed_attempts >= 4 THEN NULL ELSE code_hash END
                       WHERE email = ?""", (email,),
                )
                await connection.commit()
                return False
            cursor = await connection.execute(
                """UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND lower(email) = ? AND email_verified_at IS NOT NULL""",
                (password_hash, row[0], email),
            )
            if cursor.rowcount != 1:
                return False
            await connection.execute("DELETE FROM user_sessions WHERE user_id = ?", (row[0],))
            await connection.execute(
                "UPDATE password_reset_codes SET code_hash = NULL WHERE email = ?", (email,),
            )
            await connection.commit()
            return True
