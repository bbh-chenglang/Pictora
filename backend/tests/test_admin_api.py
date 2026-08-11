import asyncio
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password
from app.database import initialize_database
from app.dependencies import (
    get_admin_repository,
    get_current_user,
    get_user_repository,
)
from app.main import app
from app.repositories.admin_repository import AdminRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import StoredSessionUser


@pytest.fixture
def admin_client(tmp_path: Path):
    database_path = tmp_path / "admin.db"
    asyncio.run(initialize_database(database_path))
    user_repository = UserRepository(database_path)
    admin = asyncio.run(user_repository.create(
        "admin", hash_password("secret6"), email="admin@example.com", is_admin=True
    ))
    user = asyncio.run(user_repository.create(
        "alice", hash_password("secret6"), email="alice@example.com"
    ))

    async def add_usage() -> None:
        async with aiosqlite.connect(database_path) as connection:
            project_id = (await (await connection.execute(
                "SELECT id FROM projects WHERE user_id = ?", (user.id,)
            )).fetchone())[0]
            await connection.execute(
                """
                INSERT INTO history (
                    user_id, project_id, kind, status, prompt, provider, model,
                    detail, image_count, size, resolution, elapsed_ms, completed_at
                ) VALUES (?, ?, 'generate', 'completed', 'private prompt', 'openai',
                          'gpt-image-1.5', 'high', 2, '16:9', '2K', 1250,
                          CURRENT_TIMESTAMP)
                """,
                (user.id, project_id),
            )
            await connection.commit()

    asyncio.run(add_usage())
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_admin_repository] = lambda: AdminRepository(database_path)
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(
        id=admin.id,
        username=admin.username,
        email=admin.email or "",
        is_admin=True,
        api_key="",
        model="gpt-image-1.5",
    )
    try:
        with TestClient(app) as client:
            yield client, user_repository, user.id
    finally:
        app.dependency_overrides.clear()


def test_admin_lists_user_statistics_without_password_or_prompt(admin_client) -> None:
    client, _, user_id = admin_client
    response = client.get("/api/admin/users")

    assert response.status_code == 200
    alice = next(user for user in response.json() if user["id"] == user_id)
    assert alice["email"] == "alice@example.com"
    assert alice["password_status"] == "bcrypt 已加密"
    assert alice["usage_count"] == 1
    assert alice["models_used"] == ["gpt-image-1.5"]
    assert "password_hash" not in response.text
    assert "secret6" not in response.text
    assert "private prompt" not in response.text

    usage = client.get(f"/api/admin/users/{user_id}/usage").json()
    assert usage[0]["resolution"] == "2K"
    assert usage[0]["elapsed_ms"] == 1250
    assert "prompt" not in usage[0]


def test_admin_can_reset_password_and_revoke_sessions(admin_client) -> None:
    client, repository, user_id = admin_client
    response = client.post(
        f"/api/admin/users/{user_id}/reset-password",
        json={"new_password": "temporary8"},
    )

    assert response.status_code == 204
    user = asyncio.run(repository.get_by_id(user_id))
    assert user is not None
    assert verify_password("temporary8", user.password_hash)


def test_regular_user_cannot_access_admin_api(admin_client) -> None:
    client, _, user_id = admin_client
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(
        id=user_id,
        username="alice",
        email="alice@example.com",
        is_admin=False,
        api_key="",
        model="gpt-image-1.5",
    )

    response = client.get("/api/admin/users")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_required"
