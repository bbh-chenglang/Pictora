"""Tests for the documented direct.beibeihai.xyz video contract."""
from types import SimpleNamespace
import httpx
import pytest
from app.video.capabilities import VideoCatalog
from app.video.provider import VideoProvider
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
