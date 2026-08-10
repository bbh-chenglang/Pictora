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


def test_new_user_settings_have_no_default_api_config(client: TestClient) -> None:
    register(client)

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["configs"] == []
    assert payload["active_config_id"] is None
    assert payload["api_key_configured"] is False


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
    settings = client.get("/api/settings").json()
    assert settings["configs"] == []
    assert settings["active_config_id"] is None


def test_rejects_duplicate_alias_and_allows_deleting_last_config(client: TestClient) -> None:
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

    config = client.get("/api/settings").json()["configs"][0]
    response = client.delete(f"/api/settings/api-keys/{config['id']}")
    assert response.status_code == 204
    assert client.get("/api/settings").json()["configs"] == []


def test_tests_key_as_unavailable_when_upstream_returns_no_models(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client)

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            import httpx

            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={"models": []},
            )

    monkeypatch.setattr("app.api.settings.httpx.AsyncClient", FakeClient)
    created = client.post(
        "/api/settings/api-keys",
        json={"alias": "Gemini", "api_key": "secret", "provider_type": "gemini", "model": "gemini-image"},
    )

    tested = client.post(f"/api/settings/api-keys/{created.json()['id']}/test")

    assert tested.status_code == 200
    assert tested.json() == {
        "available": False,
        "message": "API Key \u4e0d\u53ef\u7528",
        "models": [],
    }


def test_discovers_models_and_tests_an_existing_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    register(client)

    class FakeClient:
        def __init__(self, **kwargs):
            self.headers = kwargs["headers"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url):
            import httpx

            assert url == "https://sub.beibeihai.xyz/v1beta/models"
            assert self.headers["x-goog-api-key"] == "secret"
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={
                    "models": [
                        {"name": "models/gemini-3.1-flash-image"},
                        {"name": "models/gemini-3.1-flash"},
                    ]
                },
            )

    monkeypatch.setattr("app.api.settings.httpx.AsyncClient", FakeClient)

    discovered = client.post(
        "/api/settings/api-keys/models",
        json={"api_key": "secret", "provider_type": "gemini"},
    )
    assert discovered.status_code == 200
    assert discovered.json() == {
        "models": [
            {"id": "models/gemini-3.1-flash-image", "provider_type": "gemini"},
            {"id": "models/gemini-3.1-flash", "provider_type": "gemini"},
        ]
    }

    created = client.post(
        "/api/settings/api-keys",
        json={"alias": "Gemini", "api_key": "secret", "provider_type": "gemini"},
    )
    config_id = created.json()["id"]
    configured_models = client.get(f"/api/settings/api-keys/{config_id}/models")
    assert configured_models.status_code == 200
    assert configured_models.json() == {
        "models": [
            {"id": "models/gemini-3.1-flash-image", "provider_type": "gemini"},
            {"id": "models/gemini-3.1-flash", "provider_type": "gemini"},
        ]
    }
    tested = client.post(f"/api/settings/api-keys/{created.json()['id']}/test")
    assert tested.status_code == 200
    assert tested.json() == {
        "available": True,
        "message": "API Key 可用",
        "models": [
            {"id": "models/gemini-3.1-flash-image", "provider_type": "gemini"},
            {"id": "models/gemini-3.1-flash", "provider_type": "gemini"},
        ],
    }


def test_saves_a_model_only_to_the_selected_config(client: TestClient) -> None:
    register(client)
    openai = client.post(
        "/api/settings/api-keys",
        json={"alias": "OpenAI", "api_key": "openai-key", "provider_type": "gpt"},
    ).json()
    gemini = client.post(
        "/api/settings/api-keys",
        json={"alias": "Gemini", "api_key": "gemini-key", "provider_type": "gemini"},
    ).json()

    updated = client.patch(
        f"/api/settings/api-keys/{gemini['id']}",
        json={"model": "gemini-custom-image"},
    )

    assert updated.status_code == 200
    configs = client.get("/api/settings").json()["configs"]
    assert next(item for item in configs if item["id"] == openai["id"])["model"] == "gpt-image-2"
    assert next(item for item in configs if item["id"] == gemini["id"])["model"] == "gemini-custom-image"


def test_openai_model_discovery_stays_on_the_openai_endpoint(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    register(client)
    client_arguments = {}

    class FakeModels:
        async def list(self):
            return type(
                "Response",
                (),
                {
                    "data": [
                        type("Model", (), {"id": "gpt-image-2"})(),
                        type("Model", (), {"id": "gpt-5"})(),
                    ]
                },
            )()

    class FakeClient:
        def __init__(self, **kwargs):
            client_arguments.update(kwargs)
            self.models = FakeModels()

        async def close(self):
            return None

    monkeypatch.setattr("app.api.settings.AsyncOpenAI", FakeClient)

    discovered = client.post(
        "/api/settings/api-keys/models",
        json={"api_key": "secret", "provider_type": "gpt"},
    )

    assert discovered.status_code == 200
    assert discovered.json() == {
        "models": [
            {"id": "gpt-image-2", "provider_type": "gpt"},
            {"id": "gpt-5", "provider_type": "gpt"},
        ]
    }
    assert str(client_arguments["base_url"]) == "https://sub.beibeihai.xyz/v1"
