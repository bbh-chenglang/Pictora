"""Request recovery never submits a paid generation, including delayed POST races."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database import initialize_database
from app.dependencies import get_current_user, get_video_service
from app.main import app
from app.schemas.auth import StoredSessionUser
from app.video.capabilities import VideoCatalog
from app.video.repository import VideoError, VideoRepository
from app.video.schemas import VideoTaskCreate
from app.video.service import VideoService

MODEL = "seedance-2.0-933-720P（秒）"
KEY = "fake-video-key"


@pytest.fixture
def state(tmp_path):
    async def setup():
        path = tmp_path / "requests.db"
        await initialize_database(path)
        repository = VideoRepository(path)
        for name in ("alice", "bob"):
            await repository.execute("INSERT INTO users(username,password_hash) VALUES(?,?)", (name, "test-hash"))
        project = await repository.execute("INSERT INTO projects(user_id,name,media_type) VALUES(1,'video','video')")
        other_project = await repository.execute("INSERT INTO projects(user_id,name,media_type) VALUES(2,'video','video')")
        key = await repository.save_key(1, "video", KEY, MODEL)
        provider = SimpleNamespace(create=AsyncMock())
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [{"id": MODEL}]}))
        service = VideoService(
            repository, Settings(_env_file=None), provider=provider,
            storage=SimpleNamespace(check=AsyncMock(return_value=True)),
            catalog=VideoCatalog("https://direct.beibeihai.xyz", transport), probe=AsyncMock(),
        )
        service.schedule = Mock()  # No worker may call the upstream generation API.
        return SimpleNamespace(repository=repository, service=service, provider=provider,
                               project=project, other_project=other_project, key=key["id"], path=path)
    return asyncio.run(setup())


def request(state, request_id=None):
    return VideoTaskCreate(request_id=request_id or uuid4(), project_id=state.project,
                           api_key_config_id=state.key, model=MODEL, prompt="scene")


@pytest.fixture
def client(state):
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(id=1, username="alice", api_key="", model="")
    app.dependency_overrides[get_video_service] = lambda: state.service
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_video_service, None)


def test_missing_request_can_be_closed_and_a_delayed_post_is_blocked(client, state):
    body = request(state).model_dump(mode="json")
    path = "/api/videos/requests/" + body["request_id"]
    assert client.get(path).json() == {"state": "missing", "task": None}
    assert client.post(path + "/resolve", json={"project_id": state.project}).json() == {"state": "closed", "task": None}
    assert client.get(path).json() == {"state": "closed", "task": None}
    assert client.post(path + "/resolve", json={"project_id": state.project}).json()["state"] == "closed"
    late = client.post("/api/videos/tasks", json=body)
    assert late.status_code == 410
    assert late.json()["error"]["code"] == "video_request_closed"
    state.service.schedule.assert_not_called()
    state.provider.create.assert_not_awaited()
    # A separate explicit submission with the current parameters can proceed.
    body["request_id"] = str(uuid4())
    assert client.post("/api/videos/tasks", json=body).status_code == 202
    state.service.schedule.assert_called_once()


def test_accepted_request_is_found_without_restarting_or_changing_it(client, state):
    body = request(state).model_dump(mode="json")
    created = client.post("/api/videos/tasks", json=body).json()["task"]
    state.service.schedule.reset_mock()
    path = "/api/videos/requests/" + body["request_id"]
    found = client.get(path)
    assert found.status_code == 200
    assert found.json() == {"state": "accepted", "task": created}
    resolved = client.post(path + "/resolve", json={"project_id": state.project})
    assert resolved.json() == found.json()
    assert KEY not in resolved.text
    state.service.schedule.assert_not_called()
    state.provider.create.assert_not_awaited()


def test_resolution_is_scoped_to_the_authenticated_user_and_owned_project(client, state):
    body = request(state).model_dump(mode="json")
    path = "/api/videos/requests/" + body["request_id"]
    response = client.post(path + "/resolve", json={"project_id": state.other_project})
    assert response.status_code == 404
    assert client.get(path).json()["state"] == "missing"
    client.post("/api/videos/tasks", json=body)
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(id=2, username="bob", api_key="", model="")
    assert client.get(path).json()["state"] == "missing"
    assert client.post(path + "/resolve", json={"project_id": state.other_project}).json()["state"] == "closed"
    # Bob's closure must not affect Alice's task with the same UUID.
    app.dependency_overrides[get_current_user] = lambda: StoredSessionUser(id=1, username="alice", api_key="", model="")
    assert client.get(path).json()["state"] == "accepted"


def test_invalid_uuid_cannot_create_a_closure_record(client, state):
    assert client.get("/api/videos/requests/not-a-uuid").status_code == 422
    assert client.post("/api/videos/requests/not-a-uuid/resolve", json={"project_id": state.project}).status_code == 422
    assert asyncio.run(state.repository.rows("SELECT * FROM video_closed_requests")) == []


def test_resolution_does_not_require_working_storage_or_upstream(client, state):
    state.service.require_pipeline = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    path = "/api/videos/requests/" + str(uuid4()) + "/resolve"
    assert client.post(path, json={"project_id": state.project}).json()["state"] == "closed"
    state.service.require_pipeline.assert_not_awaited()
    state.provider.create.assert_not_awaited()


def test_existing_request_cannot_be_resolved_from_a_different_owned_project(client, state):
    body = request(state).model_dump(mode="json")
    client.post("/api/videos/tasks", json=body)
    project = asyncio.run(state.repository.execute("INSERT INTO projects(user_id,name,media_type) VALUES(1,'another video','video')"))
    response = client.post("/api/videos/requests/" + body["request_id"] + "/resolve", json={"project_id": project})
    assert response.status_code == 409
    assert asyncio.run(state.repository.rows("SELECT * FROM video_closed_requests")) == []


@pytest.mark.asyncio
async def test_closure_blocks_a_submission_already_inside_preflight(state):
    req = request(state)
    entered, release = asyncio.Event(), asyncio.Event()
    async def paused_preflight():
        entered.set()
        await release.wait()
    state.service.require_pipeline = paused_preflight
    creating = asyncio.create_task(state.service.create(1, req))
    await entered.wait()
    assert await state.repository.resolve_request(1, req.request_id, state.project) == {"state": "closed", "task": None}
    release.set()
    with pytest.raises(VideoError) as error:
        await creating
    assert error.value.code == "video_request_closed"
    assert await state.repository.rows("SELECT id FROM video_tasks") == []
    state.service.schedule.assert_not_called()
    state.provider.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_creation_and_resolution_are_serialized_in_either_order(state):
    for _ in range(8):
        req = request(state)
        created, resolved = await asyncio.gather(
            state.service.create(1, req), state.repository.resolve_request(1, req.request_id, state.project),
            return_exceptions=True,
        )
        if isinstance(created, VideoError):
            assert created.code == "video_request_closed"
            assert resolved == {"state": "closed", "task": None}
        else:
            assert isinstance(created, dict)
            assert resolved["state"] == "accepted"
            assert resolved["task"]["id"] == created["id"]
            # Allow the next iteration without involving a real worker.
            await state.repository.update_task(created["id"], status="failed")
    state.provider.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_additive_schema_upgrade_preserves_existing_tasks_and_keys(state):
    created = await state.service.create(1, request(state))
    await state.repository.execute("DROP TABLE video_closed_requests")
    await initialize_database(state.path)
    assert (await state.repository.get_task(1, created["id"]))["model"] == MODEL
    assert (await state.repository.get_key(1, state.key))["api_key"] == KEY
    assert await state.repository.rows("SELECT * FROM video_closed_requests") == []
