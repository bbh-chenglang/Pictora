"""Tests for the documented direct.beibeihai.xyz video contract."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import httpx
import pytest
from app.video.capabilities import VideoCatalog, bundled_models, live_model, parse_model_capabilities
from app.video.provider import VideoProvider
from app.video.repository import VideoError
from app.video.schemas import VideoTaskCreate
from app.video.service import VideoService
from app.config import Settings
KEY = "video-secret"
ROOT = "https://direct.beibeihai.xyz"
def settings(): return SimpleNamespace(video_api_base_url=ROOT, video_poll_interval=0.001)
def model_response(requests):
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"object": "list", "data": [{"id": "seedance-2.0-933-720P（秒）", "object": "model"}, {"id": "custom-video-model", "object": "model"}]})
    return httpx.MockTransport(respond)
@pytest.mark.asyncio
async def test_model_catalog_uses_authenticated_v1_models_and_key_cache():
    requests=[]; catalog=VideoCatalog(ROOT, model_response(requests)); models=await catalog.get(KEY, force=True)
    assert [item["id"] for item in models] == ["seedance-2.0-933-720P（秒）", "custom-video-model"]
    assert models[0]["reference_limits"] == {"image": 9, "video": 3, "audio": 3}
    assert str(requests[0].url) == ROOT + "/v1/models" and requests[0].headers["authorization"] == "Bearer " + KEY
    assert await catalog.get(KEY) == models and len(requests) == 1
@pytest.mark.asyncio
async def test_provider_uses_documented_paths_and_content_video_url():
    calls=[]
    def respond(request):
        calls.append(request)
        if request.method == "POST": return httpx.Response(200, json={"id":"task-1","status":"queued"})
        return httpx.Response(200, json={"id":"task-1","status":"succeeded","content":{"video_url":"https://cdn.example/video.mp4"}})
    provider=VideoProvider(settings(), httpx.MockTransport(respond)); payload={"model":"custom-video-model","duration":5,"resolution":"720p","ratio":"16:9","content":[{"type":"text","text":"scene"}]}
    assert (await provider.create(KEY,payload))["id"] == "task-1"; assert (await provider.query(KEY,"task-1"))["status"] == "succeeded"; assert await provider.content_url(KEY,"task-1") == "https://cdn.example/video.mp4"
    assert calls[0].url.path == "/api/v3/contents/generations/tasks" and calls[1].url.path == "/api/v3/contents/generations/tasks/task-1" and calls[2].url.path == calls[1].url.path
    assert calls[0].headers["content-type"] == "application/json"
@pytest.mark.asyncio
async def test_normalize_builds_documented_content_array():
    catalog=VideoCatalog(ROOT); request=SimpleNamespace(model="seedance-2.0-933-720P（秒）",prompt="老人微笑",duration=5,resolution="720p",ratio="16:9")
    payload=await catalog.normalize(request,[{"type":"image","name":"角色1","url":"https://cdn.example/person.jpg"}],key=None)
    assert payload["content"] == [{"type":"text","text":"老人微笑"},{"type":"image_url","image_url":{"url":"https://cdn.example/person.jpg"},"role":"reference_image","name":"角色1"}]


@pytest.mark.parametrize("name,base,limits,resolution", [
    ("seedance-2.0-933-720P（秒）", "seedance-2.0", (9, 3, 3), "720p"),
    ("seedance-2.0-fast-933-720P（次）", "seedance-2.0-fast", (9, 3, 3), "720p"),
    ("seedance-2.0-mini-903-720P（次）", "seedance-2.0-mini", (9, 0, 3), "720p"),
    ("seedance-2.5-301010-1K（秒）", "seedance-2.5", (30, 10, 10), "1k"),
    ("minimax-h3-933-2K（次）", "minimax-h3", (9, 3, 3), "2k"),
    ("custom-model-fast-090103-1080p(次)", "custom-model-fast", (9, 1, 3), "1080p"),
    ("custom-model-000-480P", "custom-model", (0, 0, 0), "480p"),
])
def test_parse_confirmed_model_suffixes(name, base, limits, resolution):
    assert parse_model_capabilities(name) == (
        base, dict(zip(("image", "video", "audio"), limits)), resolution,
    )
    model = live_model(name)
    assert model["id"] == name  # Submit the complete upstream id unchanged.
    assert model["reference_limits"] == dict(zip(("image", "video", "audio"), limits))


@pytest.mark.parametrize("name", [
    "custom-video-model", "model-933", "model-9333-720P", "model-30101-1K",
    "model-9x3-720P", "model-933-invalid", "model-933-0P", "-933-720P",
])
def test_unrecognized_model_codes_remain_unconfirmed(name):
    assert parse_model_capabilities(name) is None
    assert live_model(name)["reference_limits"] == {"image": None, "video": None, "audio": None}


def test_bundled_and_live_catalogs_share_limits_and_documented_resolutions():
    for model in bundled_models():
        assert model == live_model(model["id"])
        assert set(model["durations_by_resolution"]) <= {"480p", "720p", "1080p"}
    seedance = live_model("seedance-2.0-933-720P（秒）")
    assert list(seedance["durations_by_resolution"]) == ["480p", "720p"]
    assert seedance["default_resolution"] == "720p"
    mini = live_model("seedance-2.0-mini-903-720P（次）")
    assert mini["default_resolution"] == "480p"


def materials_for(kind, count):
    return [{"type": kind, "name": f"{kind}{index}", "url": f"https://cdn.example/{kind}{index}"}
            for index in range(count)]


def generation_request(model, resolution="720p"):
    return SimpleNamespace(model=model, prompt="场景", duration=5, resolution=resolution, ratio="16:9")


@pytest.mark.asyncio
@pytest.mark.parametrize("model,limits", [
    ("seedance-2.0-933-720P（秒）", {"image": 9, "video": 3, "audio": 3}),
    ("seedance-2.5-301010-1K（秒）", {"image": 30, "video": 10, "audio": 10}),
])
async def test_normalize_accepts_each_limit_and_all_material_types_together(model, limits):
    materials = [material for kind, count in limits.items() for material in materials_for(kind, count)]
    payload = await VideoCatalog(ROOT).normalize(generation_request(model), materials)
    assert len(payload["content"]) == sum(limits.values()) + 1
    assert payload["model"] == model
    for kind, count in limits.items():
        assert sum(item["type"] == kind + "_url" for item in payload["content"]) == count


@pytest.mark.asyncio
@pytest.mark.parametrize("model,kind,count", [
    ("seedance-2.0-933-720P（秒）", "image", 10),
    ("seedance-2.0-933-720P（秒）", "video", 4),
    ("seedance-2.0-933-720P（秒）", "audio", 4),
    ("seedance-2.5-301010-1K（秒）", "image", 31),
    ("seedance-2.5-301010-1K（秒）", "video", 11),
    ("seedance-2.5-301010-1K（秒）", "audio", 11),
    ("seedance-2.0-mini-903-720P（次）", "video", 1),
])
async def test_normalize_rejects_excess_and_unsupported_materials(model, kind, count):
    with pytest.raises(VideoError) as error:
        await VideoCatalog(ROOT).normalize(generation_request(model), materials_for(kind, count))
    assert error.value.code == "video_material_limit_exceeded"
    assert error.value.status == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("resolution", ["1080p", "1k", "2k"])
async def test_normalize_rejects_resolution_above_720p_maximum(resolution):
    with pytest.raises(VideoError) as error:
        await VideoCatalog(ROOT).normalize(generation_request("seedance-2.0-933-720P（秒）", resolution), [])
    assert error.value.code == "video_parameters_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize("model,counts", [
    ("seedance-2.0-933-720P（秒）", (9, 3, 3)),
    ("seedance-2.5-301010-1K（秒）", (30, 10, 10)),
    ("seedance-2.0-mini-903-720P（次）", (9, 0, 3)),
])
@pytest.mark.parametrize("excess", [False, True])
async def test_submission_entry_accepts_confirmed_limits_and_blocks_excess_before_scheduling(tmp_path, model, counts, excess):
    repository = SimpleNamespace(
        database_path=tmp_path / "test.db",
        existing_request=AsyncMock(return_value=None),
        get_key=AsyncMock(return_value={"api_key": KEY}),
        rows=AsyncMock(return_value=[{"id": 1}]),
        create_task=AsyncMock(return_value=(1, True)),
        get_task=AsyncMock(return_value={"id": 1, "status": "queued"}),
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{"id": model}]}))
    provider = SimpleNamespace(create=AsyncMock())
    service = VideoService(
        repository, Settings(_env_file=None),
        storage=SimpleNamespace(check=AsyncMock(return_value=True)),
        provider=provider, catalog=VideoCatalog(ROOT, transport), probe=AsyncMock(),
    )
    service.schedule = Mock()  # Do not start a worker or send a paid request.
    materials = [material for kind, count in zip(("image", "video", "audio"), counts)
                 for material in materials_for(kind, count)]
    if excess:
        if len(materials) == 50:
            materials.pop(0)  # Exercise the per-type limit within the schema's total limit.
        materials += materials_for("video", counts[1] + 1)[-1:]
    request = VideoTaskCreate(
        request_id=uuid4(), project_id=1, api_key_config_id=1, model=model,
        prompt="场景", duration=5, resolution="720p", ratio="16:9", materials=materials,
    )
    if excess:
        with pytest.raises(VideoError) as error:
            await service.create(1, request)
        assert error.value.code == "video_material_unsupported"
        repository.create_task.assert_not_awaited()
        service.schedule.assert_not_called()
    else:
        assert await service.create(1, request) == {"id": 1, "status": "queued"}
        payload = repository.create_task.await_args.args[3]
        assert payload["model"] == model
        assert len(payload["content"]) == sum(counts) + 1
        service.schedule.assert_called_once_with(1, 1)
    provider.create.assert_not_awaited()
