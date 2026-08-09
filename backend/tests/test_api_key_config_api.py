import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import initialize_database
from app.dependencies import (
    get_api_key_config_repository,
    get_settings_repository,
    get_user_repository,
)
from app.main import app
from app.repositories.api_key_config_repository import ApiKeyConfigRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.user_repository import UserRepository


@pytest.fixture
def client(tmp_path: Path):
    database_path = tmp_path / "api-key-configs.db"
    asyncio.run(initialize_database(database_path))
    app.dependency_overrides[get_user_repository] = lambda: UserRepository(database_path)
    app.dependency_overrides[get_settings_repository] = lambda: SettingsRepository(database_path)
    app.dependency_overrides[get_api_key_config_repository] = lambda: ApiKeyConfigRepository(database_path)
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def register(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={
            "username": "alice",
            "password": "secret6",
            "password_confirmation": "secret6",
        },
    )
    assert response.status_code == 201


def test_settings_lists_sanitized_configs(client: TestClient) -> None:
    register(client)

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configs"][0]["alias"] == "默认配置"
    assert payload["configs"][0]["api_key_configured"] is False
    assert "api_key" not in payload["configs"][0]


def test_can_create_activate_update_and_delete_config(client: TestClient) -> None:
    register(client)
    created = client.post(
        "/api/settings/api-keys",
        json={
            "alias": "Gemini 1K",
            "api_key": "gemini-secret",
            "provider_type": "gemini",
        },
    )

    assert created.status_code == 201
    config = created.json()
    assert config["api_key_configured"] is True
    assert "api_key" not in config
    assert config["model"] == "gemini-3.1-flash-image"

    config_id = config["id"]
    active = client.put("/api/settings/active", json={"config_id": config_id})
    assert active.status_code == 200
    assert active.json()["active_config_id"] == config_id

    updated = client.patch(
        f"/api/settings/api-keys/{config_id}",
        json={"alias": "Gemini Final", "api_key": ""},
    )
    assert updated.status_code == 200
    assert updated.json()["alias"] == "Gemini Final"
    assert updated.json()["model"] == "gemini-3.1-flash-image"
    assert updated.json()["api_key_configured"] is True

    deleted = client.delete(f"/api/settings/api-keys/{config_id}")
    assert deleted.status_code == 204


def test_rejects_duplicate_alias_and_deleting_last_config(client: TestClient) -> None:
    register(client)
    payload = {
        "alias": "工作 Key",
        "api_key": "secret",
        "provider_type": "gpt",
    }
    assert client.post("/api/settings/api-keys", json=payload).status_code == 201
    duplicate = client.post("/api/settings/api-keys", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "api_key_alias_taken"

    configs = client.get("/api/settings").json()["configs"]
    for config in configs[:-1]:
        assert client.delete(f"/api/settings/api-keys/{config['id']}").status_code == 204
    last = configs[-1]
    response = client.delete(f"/api/settings/api-keys/{last['id']}")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_api_key_config"


def test_tests_key_as_unavailable_when_no_model_matches_provider_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client)

    class FakeModels:
        async def list(self):
            return type("Response", (), {"data": [type("Model", (), {"id": "gpt-image-2"})()]})()

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

        async def close(self):
            return None

    monkeypatch.setattr("app.api.settings.AsyncOpenAI", FakeClient)
    created = client.post(
        "/api/settings/api-keys",
        json={"alias": "Gemini", "api_key": "secret", "provider_type": "gemini", "model": "gemini-image"},
    )

    tested = client.post(f"/api/settings/api-keys/{created.json()['id']}/test")

    assert tested.status_code == 200
    assert tested.json() == {"available": False, "message": "API Key \u4e0d\u53ef\u7528"}


def test_discovers_models_and_tests_an_existing_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client)

    class FakeModels:
        async def list(self):
            return type("Response", (), {"data": [type("Model", (), {"id": "gemini-3.1-flash-image"})()]})()

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

        async def close(self):
            return None

    monkeypatch.setattr("app.api.settings.AsyncOpenAI", FakeClient)

    discovered = client.post("/api/settings/api-keys/models", json={"api_key": "secret"})
    assert discovered.status_code == 200
    assert discovered.json() == {
        "models": [{"id": "gemini-3.1-flash-image", "provider_type": "gemini"}]
    }

    created = client.post(
        "/api/settings/api-keys",
        json={"alias": "Gemini", "api_key": "secret", "provider_type": "gemini"},
    )
    config_id = created.json()["id"]
    configured_models = client.get(f"/api/settings/api-keys/{config_id}/models")
    assert configured_models.status_code == 200
    assert configured_models.json() == {
        "models": [{"id": "gemini-3.1-flash-image", "provider_type": "gemini"}]
    }
    tested = client.post(f"/api/settings/api-keys/{created.json()['id']}/test")
    assert tested.status_code == 200
    assert tested.json() == {"available": True, "message": "API Key 可用"}
