import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.dependencies import (
    get_email_sender,
    get_user_repository,
    get_verification_code_repository,
)
from app.main import app
from app.repositories.user_repository import UserRepository
from app.auth import hash_password
from app.repositories.verification_code_repository import VerificationCodeRepository


class FakeEmailSender:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    async def send_verification_code(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "auth-api.db"
    asyncio.run(initialize_database(database_path))
    repository = UserRepository(database_path)
    code_repository = VerificationCodeRepository(database_path)
    sender = FakeEmailSender()
    app.dependency_overrides[get_user_repository] = lambda: repository
    app.dependency_overrides[get_verification_code_repository] = lambda: code_repository
    app.dependency_overrides[get_email_sender] = lambda: sender
    try:
        with TestClient(app) as test_client:
            test_client.verification_codes = sender.codes
            yield test_client
    finally:
        app.dependency_overrides.clear()


def register(client: TestClient, username: str = "alice", email: str = "alice@example.com"):
    code_response = client.post("/api/auth/verification-code", json={"email": email})
    assert code_response.status_code == 200
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "verification_code": client.verification_codes[email],
            "password": "secret6",
            "password_confirmation": "secret6",
        },
    )


def test_register_creates_session_and_authenticates_client(client: TestClient) -> None:
    response = register(client)

    assert response.status_code == 201
    assert response.cookies.get("genimage_session")
    assert client.get("/api/auth/me").json() == {
        "username": "alice",
        "email": "alice@example.com",
        "is_admin": False,
        "api_key_configured": False,
    }
    assert "secret6" not in response.text


def test_register_rejects_duplicate_username(client: TestClient) -> None:
    assert register(client).status_code == 201

    response = register(client, email="alice2@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "username_taken"


def test_protected_endpoint_requires_login_and_logout_invalidates_session(
    client: TestClient,
) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert register(client).status_code == 201

    assert client.post("/api/auth/logout").status_code == 204
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_login_and_password_change_revoke_old_session(client: TestClient) -> None:
    assert register(client).status_code == 201
    client.post("/api/auth/logout")

    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "secret6"},
    )
    assert response.status_code == 200

    response = client.put(
        "/api/auth/password",
        json={
            "old_password": "secret6",
            "new_password": "changed6",
            "new_password_confirmation": "changed6",
        },
    )
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "changed6"},
    )
    assert response.status_code == 200


def test_register_rejects_mismatched_or_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "verification_code": "123456",
            "password": "short",
            "password_confirmation": "short",
        },
    )
    assert response.status_code == 422

    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "verification_code": "123456",
            "password": "secret6",
            "password_confirmation": "different6",
        },
    )
    assert response.status_code == 422


def test_register_requires_the_emailed_code(client: TestClient) -> None:
    assert client.post(
        "/api/auth/verification-code", json={"email": "alice@example.com"}
    ).status_code == 200

    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "verification_code": "000000",
            "password": "secret6",
            "password_confirmation": "secret6",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_verification_code"


def test_legacy_user_binds_email_and_keeps_the_same_account(client: TestClient) -> None:
    repository = app.dependency_overrides[get_user_repository]()
    legacy = asyncio.run(repository.create("legacy", hash_password("oldpass6")))
    email = "legacy@example.com"
    assert client.post("/api/auth/verification-code", json={"email": email}).status_code == 200

    response = client.post(
        "/api/auth/register",
        json={
            "username": "legacy",
            "email": email,
            "verification_code": client.verification_codes[email],
            "password": "oldpass6",
            "password_confirmation": "oldpass6",
        },
    )

    assert response.status_code == 201
    migrated = asyncio.run(repository.get_by_email(email))
    assert migrated is not None
    assert migrated.id == legacy.id


def test_configured_admin_email_receives_admin_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "admin@example.com, second@example.com")

    response = register(client, username="admin", email="admin@example.com")

    assert response.status_code == 201
    assert response.json()["is_admin"] is True
    assert client.get("/api/auth/me").json()["is_admin"] is True


def test_verification_code_requests_are_rate_limited(client: TestClient) -> None:
    email = "alice@example.com"
    assert client.post("/api/auth/verification-code", json={"email": email}).status_code == 200

    response = client.post("/api/auth/verification-code", json={"email": email})

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "verification_code_cooldown"
