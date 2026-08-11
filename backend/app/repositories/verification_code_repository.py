from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from app.auth import verify_password
from app.database import DATABASE_PATH


class VerificationCodeCooldownError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds


class VerificationCodeRepository:
    def __init__(self, database_path: Path = DATABASE_PATH) -> None:
        self.database_path = database_path

    async def store(
        self,
        email: str,
        code_hash: str,
        *,
        ttl_seconds: int,
        cooldown_seconds: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            row = await (await connection.execute(
                "SELECT last_sent_at FROM email_verification_codes WHERE email = ?",
                (email,),
            )).fetchone()
            if row is not None:
                last_sent_at = datetime.fromisoformat(row[0])
                if last_sent_at.tzinfo is None:
                    last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)
                elapsed = (now - last_sent_at).total_seconds()
                if elapsed < cooldown_seconds:
                    await connection.rollback()
                    raise VerificationCodeCooldownError(max(1, int(cooldown_seconds - elapsed)))
            await connection.execute(
                """
                INSERT INTO email_verification_codes (
                    email, code_hash, expires_at, last_sent_at, failed_attempts
                ) VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(email) DO UPDATE SET
                    code_hash = excluded.code_hash,
                    expires_at = excluded.expires_at,
                    last_sent_at = excluded.last_sent_at,
                    failed_attempts = 0
                """,
                (
                    email,
                    code_hash,
                    (now + timedelta(seconds=ttl_seconds)).isoformat(),
                    now.isoformat(),
                ),
            )
            await connection.commit()

    async def verify(self, email: str, code: str) -> bool:
        now = datetime.now(timezone.utc)
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute("BEGIN IMMEDIATE")
            row = await (await connection.execute(
                """
                SELECT code_hash, expires_at, failed_attempts
                FROM email_verification_codes WHERE email = ?
                """,
                (email,),
            )).fetchone()
            if row is None:
                await connection.rollback()
                return False
            expires_at = datetime.fromisoformat(row[1])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now or int(row[2]) >= 5:
                await connection.execute(
                    "DELETE FROM email_verification_codes WHERE email = ?", (email,)
                )
                await connection.commit()
                return False
            if not verify_password(code, row[0]):
                await connection.execute(
                    """
                    UPDATE email_verification_codes
                    SET failed_attempts = failed_attempts + 1
                    WHERE email = ?
                    """,
                    (email,),
                )
                await connection.commit()
                return False
            await connection.rollback()
            return True

    async def delete(self, email: str) -> None:
        async with aiosqlite.connect(self.database_path) as connection:
            await connection.execute(
                "DELETE FROM email_verification_codes WHERE email = ?", (email,)
            )
            await connection.commit()
