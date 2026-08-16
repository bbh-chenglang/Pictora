import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.dependencies import (
    get_auth_rate_limiter,
    get_email_sender,
    get_prompt_repository,
    get_user_repository,
    get_verification_code_repository,
)
from app.main import app
from app.repositories.prompt_repository import PromptRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_code_repository import VerificationCodeRepository
from app.services.auth_rate_limiter import AuthRateLimiter


class FakeEmailSender:
    def __init__(self) -> None:
        self.codes: dict[str, str] = {}

    async def send_verification_code(self, email: str, code: str) -> None:
        self.codes[email] = code


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "prompts.db"
    asyncio.run(initialize_database(database_path))
    user_repository = UserRepository(database_path)
    code_repository = VerificationCodeRepository(database_path)
    prompt_repository = PromptRepository(database_path)
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
    app.dependency_overrides[get_prompt_repository] = lambda: prompt_repository
    try:
        with TestClient(app) as test_client:
            test_client.codes = sender.codes
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


def prompt_payload(name: str = "商品棚拍") -> dict[str, str]:
    return {"name": name, "prompt": "一张干净的商品棚拍，主体是红色水壶", "category": "product"}


def test_prompt_crud_search_and_category_filter(client: TestClient) -> None:
    register(client)
    created = client.post("/api/prompts", json=prompt_payload())
    assert created.status_code == 201
    prompt = created.json()
    assert prompt["name"] == "商品棚拍"
    assert client.get("/api/prompts?search=水壶&category=product").json()[0]["id"] == prompt["id"]
    assert client.get("/api/prompts?category=portrait").json() == []

    updated = client.patch(
        f"/api/prompts/{prompt['id']}",
        json={**prompt_payload("更新后的棚拍"), "category": "我的商品模板"},
    )
    assert updated.status_code == 200
    assert updated.json()["category"] == "我的商品模板"
    assert client.get("/api/prompts?category=我的商品模板").json()[0]["id"] == prompt["id"]
    empty_category = client.post(
        "/api/prompts",
        json={"name": "未分类提示词", "prompt": "快速记录的一段提示词"},
    )
    assert empty_category.status_code == 201
    assert empty_category.json()["category"] == ""
    assert client.get("/api/prompts?category=我的商品模板").json()[0]["category"] == "我的商品模板"
    assert client.delete(f"/api/prompts/{prompt['id']}").status_code == 204
    assert client.get(f"/api/prompts/{prompt['id']}").status_code == 404


def test_prompt_data_is_private_to_owner(client: TestClient) -> None:
    register(client, "alice")
    prompt = client.post("/api/prompts", json=prompt_payload()).json()
    client.post("/api/auth/logout")
    register(client, "bob")
    assert client.get(f"/api/prompts/{prompt['id']}").status_code == 404
    assert client.patch(f"/api/prompts/{prompt['id']}", json=prompt_payload("越权")).status_code == 404
    assert client.delete(f"/api/prompts/{prompt['id']}").status_code == 404
    client.post("/api/auth/logout")
    assert client.get("/api/prompts").status_code == 401
