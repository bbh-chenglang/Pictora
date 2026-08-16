import asyncio
import json
from pathlib import Path

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import initialize_database
from app.dependencies import (
    get_auth_rate_limiter,
    get_current_admin,
    get_current_user,
    get_email_sender,
    get_skill_repository,
    get_user_repository,
    get_verification_code_repository,
)
from app.main import app
from app.repositories.skill_repository import SkillRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_code_repository import VerificationCodeRepository
from app.schemas.auth import StoredSessionUser
from app.services.auth_rate_limiter import AuthRateLimiter


class FakeEmailSender:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    async def send_verification_code(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "skills.db"
    asyncio.run(initialize_database(database_path))
    user_repository = UserRepository(database_path)
    code_repository = VerificationCodeRepository(database_path)
    skill_repository = SkillRepository(database_path)
    sender = FakeEmailSender()
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_verification_code_repository] = lambda: code_repository
    app.dependency_overrides[get_email_sender] = lambda: sender
    app.dependency_overrides[get_auth_rate_limiter] = lambda: AuthRateLimiter(
        login_max_failures=5,
        login_window_seconds=900,
        verification_max_requests_per_ip=10,
        verification_global_max_requests=100,
        verification_window_seconds=600,
    )
    app.dependency_overrides[get_skill_repository] = lambda: skill_repository
    try:
        with TestClient(app) as test_client:
            test_client.codes = sender.codes
            test_client.user_repository = user_repository
            test_client.database_path = database_path
            yield test_client
    finally:
        app.dependency_overrides.clear()


def register(client: TestClient, username: str = "alice") -> None:
    email = f"{username}@example.com"
    assert client.post("/api/auth/verification-code", json={"email": email}).status_code == 200
    response = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "verification_code": client.codes[email],
            "password": "secret6",
            "password_confirmation": "secret6",
        },
    )
    assert response.status_code == 201


def workflow() -> dict[str, object]:
    return {
        "prompt_template": "一张高质感商品棚拍，主体：{{subject}}",
        "provider_type": "gpt",
        "model": "gpt-image-1.5",
        "quality": "high",
        "size": "1024x1024",
        "resolution": "",
        "image_count": 2,
        "reference_requirements": ["object"],
        "multi_view": {"enabled": False, "target": "person", "preset_keys": [], "custom_views": []},
    }


def create_skill(client: TestClient):
    return client.post(
        "/api/skills",
        data={
            "title": "商品棚拍",
            "description": "用于电商商品的干净棚拍",
            "category": "product",
            "workflow_json": json.dumps(workflow()),
        },
        files={"cover": ("cover.png", b"fake-image", "image/png")},
    )


def test_skill_lifecycle_and_published_visibility(client: TestClient) -> None:
    register(client)
    response = create_skill(client)
    assert response.status_code == 201
    skill = response.json()
    assert skill["status"] == "draft"
    assert skill["has_cover"] is True
    assert client.get("/api/skills?scope=discover").json() == []

    assert client.post(f"/api/skills/{skill['id']}/submit").status_code == 200
    assert client.get("/api/skills?scope=discover").json() == []

    admin = StoredSessionUser(id=99, username="admin", email="admin@example.com", is_admin=True, api_key="", model="gpt-image-1.5")
    app.dependency_overrides[get_current_admin] = lambda: admin
    approved = client.post(f"/api/skills/{skill['id']}/review", json={"decision": "published", "note": "通过"})
    assert approved.status_code == 200
    app.dependency_overrides.pop(get_current_admin, None)

    discover = client.get("/api/skills?scope=discover")
    assert discover.status_code == 200
    assert discover.json()[0]["title"] == "商品棚拍"
    assert client.get(f"/api/skills/{skill['id']}/cover").content == b"fake-image"


def test_skill_favorite_use_and_owner_isolation(client: TestClient) -> None:
    register(client, "alice")
    skill = create_skill(client).json()
    admin = StoredSessionUser(id=99, username="admin", email="admin@example.com", is_admin=True, api_key="", model="gpt-image-1.5")
    app.dependency_overrides[get_current_admin] = lambda: admin
    assert client.post(f"/api/skills/{skill['id']}/review", json={"decision": "published"}).status_code == 409
    assert client.post(f"/api/skills/{skill['id']}/submit").status_code == 200
    assert client.post(f"/api/skills/{skill['id']}/review", json={"decision": "published"}).status_code == 200
    app.dependency_overrides.pop(get_current_admin, None)

    assert client.put(f"/api/skills/{skill['id']}/favorite").json()["favorite_count"] == 1
    used = client.post(f"/api/skills/{skill['id']}/use").json()
    assert used["workflow"]["prompt_template"].startswith("一张高质感")
    assert used["skill"]["use_count"] == 1
    assert client.delete(f"/api/skills/{skill['id']}/favorite").json()["favorite_count"] == 0


def test_skill_rejects_non_image_or_oversized_cover(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/skills",
        data={"title": "坏封面", "description": "测试", "category": "other", "workflow_json": json.dumps(workflow())},
        files={"cover": ("cover.txt", b"text", "text/plain")},
    )
    assert response.status_code == 415


def test_admin_can_delete_published_skill_but_regular_user_cannot(client: TestClient) -> None:
    register(client, "alice")
    skill = create_skill(client).json()
    admin = StoredSessionUser(
        id=99,
        username="admin",
        email="admin@example.com",
        is_admin=True,
        api_key="",
        model="gpt-image-1.5",
    )
    app.dependency_overrides[get_current_admin] = lambda: admin
    assert client.post(f"/api/skills/{skill['id']}/submit").status_code == 200
    assert client.post(f"/api/skills/{skill['id']}/review", json={"decision": "published"}).status_code == 200
    app.dependency_overrides.pop(get_current_admin, None)

    regular_delete = client.delete(f"/api/skills/{skill['id']}")
    assert regular_delete.status_code == 409
    assert client.put(f"/api/skills/{skill['id']}/favorite").status_code == 200
    assert client.post(f"/api/skills/{skill['id']}/use").status_code == 200

    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        admin_delete = client.delete(f"/api/skills/{skill['id']}")
        assert admin_delete.status_code == 204
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert client.get(f"/api/skills/{skill['id']}").status_code == 404

    async def related_rows() -> tuple[int, int]:
        async with aiosqlite.connect(client.database_path) as connection:
            favorites = await (await connection.execute(
                "SELECT COUNT(*) FROM skill_favorites WHERE skill_id = ?", (skill["id"],)
            )).fetchone()
            uses = await (await connection.execute(
                "SELECT COUNT(*) FROM skill_uses WHERE skill_id = ?", (skill["id"],)
            )).fetchone()
        return int(favorites[0]), int(uses[0])

    assert asyncio.run(related_rows()) == (0, 0)
