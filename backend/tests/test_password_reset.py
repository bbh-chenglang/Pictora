import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, hash_session_token, verify_password
from app.config import Settings
from app.database import SCHEMA_VERSION, initialize_database
from app.dependencies import (
    get_auth_rate_limiter, get_email_sender, get_password_reset_repository,
    get_user_repository, get_verification_code_repository,
)
from app.main import app
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_code_repository import VerificationCodeRepository
from app.services.auth_rate_limiter import AuthRateLimiter
from app.services.email_sender import EmailDeliveryError, EmailSender


class FakeEmailSender:
    def __init__(self):
        self.codes = {}
        self.fail = False

    def ensure_configured(self):
        pass

    async def send_password_reset_code(self, email, code):
        if self.fail:
            raise EmailDeliveryError("sensitive SMTP details")
        self.codes[email] = code


def limiter(**overrides):
    return AuthRateLimiter(**{
        "login_max_failures": 20,
        "login_window_seconds": 900,
        "verification_max_requests_per_ip": 30,
        "verification_global_max_requests": 100,
        "verification_window_seconds": 600,
        **overrides,
    })


@pytest.fixture
def reset_client(tmp_path, monkeypatch):
    path = tmp_path / "reset.db"
    asyncio.run(initialize_database(path))
    users = UserRepository(path)
    user = asyncio.run(users.create("alice", hash_password("secret6"), email="alice@example.com"))
    sender = FakeEmailSender()
    monkeypatch.setattr("app.api.auth.new_verification_code", lambda: "123456")
    app.dependency_overrides[get_user_repository] = lambda: users
    app.dependency_overrides[get_password_reset_repository] = lambda: PasswordResetRepository(path)
    app.dependency_overrides[get_verification_code_repository] = lambda: VerificationCodeRepository(path)
    app.dependency_overrides[get_email_sender] = lambda: sender
    rate_limiter = limiter()
    app.dependency_overrides[get_auth_rate_limiter] = lambda: rate_limiter
    try:
        with TestClient(app) as client:
            client.database_path = path
            client.sender = sender
            client.users = users
            client.user_id = user.id
            yield client
    finally:
        app.dependency_overrides.clear()


def send_code(client, email="alice@example.com"):
    return client.post("/api/auth/password-reset-code", json={"email": email})


def reset(client, code="123456", email="alice@example.com", **overrides):
    return client.post("/api/auth/reset-password", json={
        "email": email, "verification_code": code,
        "new_password": "changed6", "new_password_confirmation": "changed6",
        **overrides,
    })


def execute(client, sql, params=()):
    with sqlite3.connect(client.database_path) as connection:
        connection.execute(sql, params)


def test_reset_revokes_all_sessions_preserves_account_and_allows_new_login(reset_client):
    client = reset_client
    for token in ("first-session", "second-session"):
        asyncio.run(client.users.create_session(client.user_id, hash_session_token(token)))
    asyncio.run(client.users.update_settings(client.user_id, model="gpt-image-1.5", api_key="saved-key"))
    with sqlite3.connect(client.database_path) as connection:
        project_before = connection.execute("SELECT id, user_id, name FROM projects").fetchall()
        connection.execute(
            """INSERT INTO history (user_id, project_id, kind, status, prompt, provider, model, detail)
               VALUES (?, ?, 'generate', 'completed', 'saved prompt', 'p', 'm', 'd')""",
            (client.user_id, project_before[0][0]),
        )
        history_before = connection.execute("SELECT * FROM history").fetchall()
    client.cookies.set("genimage_session", "first-session")
    assert client.get("/api/auth/me").status_code == 200
    assert send_code(client, " Alice@Example.com ").status_code == 200
    assert client.sender.codes == {"alice@example.com": "123456"}
    response = reset(client, email=" ALICE@example.COM ")
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert client.get("/api/auth/me").status_code == 401
    for token in ("first-session", "second-session"):
        assert asyncio.run(client.users.get_session_user(hash_session_token(token))) is None
    with sqlite3.connect(client.database_path) as connection:
        assert connection.execute("SELECT id, user_id, name FROM projects").fetchall() == project_before
        assert connection.execute("SELECT * FROM history").fetchall() == history_before
        assert connection.execute("SELECT code_hash FROM password_reset_codes").fetchone()[0] is None
    user = asyncio.run(client.users.get_by_id(client.user_id))
    assert user.username == "alice" and user.api_key == "saved-key"
    assert user.password_hash != "changed6" and verify_password("changed6", user.password_hash)
    assert reset(client).status_code == 400
    assert client.post("/api/auth/login", json={"email": user.email, "password": "secret6"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": user.email, "password": "changed6"}).status_code == 200


def test_unknown_and_unverified_emails_have_same_response_and_cooldown(reset_client):
    client = reset_client
    asyncio.run(client.users.create("unverified", hash_password("secret6"), email="unverified@example.com"))
    execute(client, "UPDATE users SET email_verified_at = NULL WHERE username = 'unverified'")
    asyncio.run(client.users.create("legacy", hash_password("secret6")))
    responses = [send_code(client, email) for email in (
        "alice@example.com", "missing@example.com", "unverified@example.com",
    )]
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json() == responses[1].json() == responses[2].json()
    assert client.sender.codes == {"alice@example.com": "123456"}
    for email in ("alice@example.com", "missing@example.com", "unverified@example.com"):
        response = send_code(client, email)
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "verification_code_cooldown"
        assert int(response.headers["retry-after"]) > 0
    assert reset(client, email="missing@example.com").status_code == 400
    assert reset(client, email="unverified@example.com").status_code == 400
    assert send_code(client, "legacy").status_code == 422


def test_wrong_code_five_times_invalidates_code(reset_client):
    assert send_code(reset_client).status_code == 200
    for _ in range(5):
        assert reset(reset_client, code="000000").status_code == 400
    assert reset(reset_client).status_code == 400
    assert verify_password("secret6", asyncio.run(reset_client.users.get_by_id(reset_client.user_id)).password_hash)


def test_expired_code_is_rejected(reset_client):
    assert send_code(reset_client).status_code == 200
    execute(reset_client, "UPDATE password_reset_codes SET expires_at = ?", (
        (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    ))
    assert reset(reset_client).status_code == 400


def test_resend_invalidates_old_code_without_invalidating_registration_code(reset_client, monkeypatch):
    client = reset_client
    registration = VerificationCodeRepository(client.database_path)
    asyncio.run(registration.store(
        "alice@example.com", hash_password("111111"), ttl_seconds=600, cooldown_seconds=60,
    ))
    assert send_code(client).status_code == 200
    assert reset(client, code="111111").status_code == 400
    assert asyncio.run(registration.verify("alice@example.com", "111111"))
    execute(client, "UPDATE password_reset_codes SET last_sent_at = ?", (
        (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat(),
    ))
    monkeypatch.setattr("app.api.auth.new_verification_code", lambda: "654321")
    assert send_code(client).status_code == 200
    assert reset(client, code="123456").status_code == 400
    assert reset(client, code="654321").status_code == 204
    assert asyncio.run(registration.verify("alice@example.com", "111111"))


def test_registration_cannot_use_reset_code(reset_client):
    assert send_code(reset_client).status_code == 200
    response = reset_client.post("/api/auth/register", json={
        "username": "intruder", "email": "alice@example.com", "verification_code": "123456",
        "password": "secret6", "password_confirmation": "secret6",
    })
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_verification_code"


def test_concurrent_reset_succeeds_only_once(reset_client):
    assert send_code(reset_client).status_code == 200
    repository = PasswordResetRepository(reset_client.database_path)
    password_hash = hash_password("changed6")

    async def concurrent():
        return await asyncio.gather(*[
            repository.reset_password("alice@example.com", "123456", password_hash)
            for _ in range(2)
        ])

    assert sorted(asyncio.run(concurrent())) == [False, True]


def test_transaction_failure_rolls_back_password_code_and_sessions(reset_client):
    client = reset_client
    assert send_code(client).status_code == 200
    token_hash = hash_session_token("saved-session")
    asyncio.run(client.users.create_session(client.user_id, token_hash))
    execute(client, """CREATE TRIGGER reject_session_delete BEFORE DELETE ON user_sessions
                      BEGIN SELECT RAISE(ABORT, 'test rollback'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        reset(client)
    user = asyncio.run(client.users.get_by_id(client.user_id))
    assert verify_password("secret6", user.password_hash)
    assert asyncio.run(client.users.get_session_user(token_hash)) is not None
    execute(client, "DROP TRIGGER reject_session_delete")
    assert reset(client).status_code == 204


@pytest.mark.parametrize("change", [
    "UPDATE users SET email_verified_at = NULL WHERE username = 'alice'",
    "UPDATE users SET email = 'changed@example.com' WHERE username = 'alice'",
])
def test_reset_requires_the_same_verified_account_at_submission(reset_client, change):
    assert send_code(reset_client).status_code == 200
    execute(reset_client, change)
    assert reset(reset_client).status_code == 400
    user = asyncio.run(reset_client.users.get_by_id(reset_client.user_id))
    assert verify_password("secret6", user.password_hash)


def test_delivery_failure_revokes_only_its_code_and_keeps_cooldown(reset_client, caplog):
    client = reset_client
    client.sender.fail = True
    assert send_code(client).status_code == 200
    assert "Password reset email delivery failed" in caplog.text
    assert "123456" not in caplog.text and "sensitive SMTP details" not in caplog.text
    assert reset(client).status_code == 400
    assert send_code(client).status_code == 429
    execute(client, "UPDATE password_reset_codes SET last_sent_at = ?", (
        (datetime.now(timezone.utc) - timedelta(seconds=61)).isoformat(),
    ))
    client.sender.fail = False
    assert send_code(client).status_code == 200
    assert reset(client).status_code == 204


def test_late_invalidation_does_not_remove_replacement(reset_client):
    repository = PasswordResetRepository(reset_client.database_path)
    assert send_code(reset_client).status_code == 200
    asyncio.run(repository.invalidate("alice@example.com", "old-hash"))
    assert reset(reset_client).status_code == 204


def test_missing_smtp_configuration_is_the_same_for_unknown_email(reset_client):
    sender = EmailSender(Settings(smtp_username="", smtp_app_password="", smtp_sender=""))
    app.dependency_overrides[get_email_sender] = lambda: sender
    for email in ("alice@example.com", "missing@example.com"):
        response = send_code(reset_client, email)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "smtp_not_configured"


@pytest.mark.parametrize("overrides", [
    {"new_password": "short", "new_password_confirmation": "short"},
    {"new_password_confirmation": "different6"},
    {"verification_code": "12345"},
    {"email": "invalid"},
    {"unexpected": True},
])
def test_invalid_reset_payload_is_rejected(reset_client, overrides):
    assert reset(reset_client, **overrides).status_code == 422


def test_reset_rate_limit_is_independent_of_login_and_limits_clients(reset_client):
    rate_limiter = limiter(login_max_failures=2)
    app.dependency_overrides[get_auth_rate_limiter] = lambda: rate_limiter
    assert reset(reset_client).status_code == 400
    assert reset(reset_client).status_code == 400
    for email in ("alice@example.com", "other@example.com"):
        response = reset(reset_client, email=email)
        assert response.status_code == 429
        assert response.headers["retry-after"]
    assert reset_client.post("/api/auth/login", json={
        "email": "alice@example.com", "password": "secret6",
    }).status_code == 200


def test_reset_rate_limit_tracks_email_across_clients_and_expires():
    now = [0.0]
    rate_limiter = limiter(login_max_failures=2, clock=lambda: now[0])
    assert rate_limiter.consume_password_reset_request("alice", "ip1") == 0
    assert rate_limiter.consume_password_reset_request("alice", "ip2") == 0
    assert rate_limiter.consume_password_reset_request("alice", "ip3") == 900
    now[0] = 901
    assert rate_limiter.consume_password_reset_request("alice", "ip3") == 0


@pytest.mark.parametrize("limits", [
    {"verification_max_requests_per_ip": 1}, {"verification_global_max_requests": 1},
])
def test_reset_email_requests_share_registration_send_limits(reset_client, limits):
    rate_limiter = limiter(**limits)
    app.dependency_overrides[get_auth_rate_limiter] = lambda: rate_limiter
    assert send_code(reset_client).status_code == 200
    response = reset_client.post("/api/auth/verification-code", json={"email": "other@example.com"})
    assert response.status_code == 429
    assert send_code(reset_client, "missing@example.com").status_code == 429


@pytest.mark.asyncio
async def test_database_upgrades_version_19_and_repeated_initialization_preserves_data(tmp_path: Path):
    path = tmp_path / "upgrade.db"
    await initialize_database(path)
    users = UserRepository(path)
    user = await users.create("alice", hash_password("secret6"), email="alice@example.com")
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE password_reset_codes")
        connection.execute("PRAGMA user_version = 19")
    await initialize_database(path)
    repository = PasswordResetRepository(path)
    code_hash = hash_password("123456")
    await repository.store("alice@example.com", user.id, code_hash, ttl_seconds=600, cooldown_seconds=60)
    await initialize_database(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 20
        assert connection.execute("SELECT code_hash FROM password_reset_codes").fetchone()[0] == code_hash
        assert connection.execute("SELECT COUNT(*) FROM projects WHERE user_id = ?", (user.id,)).fetchone()[0] == 1
    assert (await users.get_by_id(user.id)).password_hash == user.password_hash


@pytest.mark.asyncio
async def test_email_sender_uses_password_reset_subject_and_content(monkeypatch):
    sender = EmailSender(Settings(
        smtp_username="sender@example.com", smtp_app_password="app-password", smtp_sender="sender@example.com",
    ))
    messages = []
    monkeypatch.setattr(sender, "_send", lambda message, *_: messages.append(message))
    await sender.send_password_reset_code("alice@example.com", "123456")
    assert messages[0]["Subject"] == "Pictora 找回密码验证码"
    assert messages[0]["To"] == "alice@example.com"
    assert "123456" in messages[0].get_content()
    assert "10 分钟" in messages[0].get_content()
