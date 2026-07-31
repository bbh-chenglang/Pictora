import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.dependencies import get_user_repository
from app.main import app
from app.repositories.user_repository import UserRepository


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "auth-api.db"
    asyncio.run(initialize_database(database_path))
    repository = UserRepository(database_path)
    app.dependency_overrides[get_user_repository] = lambda: repository
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def register(client: TestClient, username: str = "alice"):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
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
        "api_key_configured": False,
    }
    assert "secret6" not in response.text


def test_register_rejects_duplicate_username(client: TestClient) -> None:
    assert register(client).status_code == 201

    response = register(client)

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
        json={"username": "alice", "password": "secret6"},
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
        json={"username": "alice", "password": "changed6"},
    )
    assert response.status_code == 200


def test_register_rejects_mismatched_or_short_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "password": "short",
            "password_confirmation": "short",
        },
    )
    assert response.status_code == 422

    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "password": "secret6",
            "password_confirmation": "different6",
        },
    )
    assert response.status_code == 422
