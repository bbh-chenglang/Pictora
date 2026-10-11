import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.database import initialize_database
from app.error_details import failure_details, local_failure_details
from app.providers.base import ProviderRequestError
from app.repositories.history_repository import HistoryRepository
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.schemas.history import GenerationTaskDetail
from app.services.history_service import HistoryService
from app.services.image_service import ImageService
from app.providers.registry import ProviderRegistry
from app.video.provider import VideoProvider
from app.video.service import VideoService


def test_nested_validation_and_redaction():
    details = failure_details({"detail": [{"loc": ["body", "duration"], "msg": "秒数必须是 5 到 10 之间的整数。 token=private https://cdn.example/?signed=secret"}]}, "submission")
    assert details["parameter"] == "body.duration"
    assert "秒数必须" in details["upstream_message"]
    assert "private" not in str(details) and "https://" not in str(details)


def test_generic_code_with_specific_message_does_not_claim_reason_is_missing():
    details = failure_details({"error": {"code": "upstream_generation_failed", "message": "时长超出模型允许范围"}}, "generation")
    assert details["reason_provided"] is True
    assert "未提供具体失败原因" not in details["suggestion"]


def test_image_error_preserves_full_cause_parameters_and_request_id():
    secret = "unprefixed-secret"
    error = ProviderRequestError(status_code=422, secret=secret, request_id="req-22", response_content=json.dumps({
        "error": {"code": "bad_size", "param": "size", "message": "尺寸超限。" * 200 + secret}
    }).encode())
    assert error.details["parameter"] == "size"
    assert error.details["upstream_request_id"] == "req-22"
    assert len(error.details["upstream_message"]) > 400
    assert secret not in str(error.details) and secret not in error.message


def test_storage_response_dictionary_is_safe_and_does_not_break_error_handling():
    error = RuntimeError("storage unavailable")
    error.response = {"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}}
    details = local_failure_details("storage", "video_operation_error", str(error), exception=error)
    assert details["http_status"] == 403 and details["service_code"] == "AccessDenied"


def test_image_transport_error_keeps_safe_actual_reason():
    error = ProviderRequestError(cause=httpx.ConnectError("DNS lookup failed for https://private.example/?token=private"))
    assert error.details["exception_type"] == "ConnectError"
    assert "DNS lookup failed" in error.details["local_message"]
    assert "private" not in error.details["local_message"]


@pytest.mark.asyncio
async def test_all_failed_images_keep_each_slots_cause():
    first = ProviderRequestError(status_code=422, response_content=b'{"error":{"message":"bad size","param":"size"}}')
    second = ProviderRequestError(status_code=403, response_content=b'{"error":{"message":"model unavailable","param":"model"}}')
    provider = SimpleNamespace(provider_id="compatible", generate_image=AsyncMock(side_effect=[first, second]))
    registry = ProviderRegistry({"compatible": provider})
    service = ImageService(registry)
    with pytest.raises(ProviderRequestError) as caught:
        await service.generate(GenerateRequest(provider="compatible", model="gpt-image-1.5", prompt="test", count=2))
    failures = caught.value.details["failures"]
    assert [(item["position"], item["error_details"]["parameter"]) for item in failures] == [(0, "size"), (1, "model")]


@pytest.mark.asyncio
async def test_image_error_survives_task_batch_history_and_database_reopen(tmp_path):
    db = tmp_path / "tasks.db"
    await initialize_database(db)
    repository = HistoryRepository(db)
    import aiosqlite
    async with aiosqlite.connect(db) as connection:
        await connection.execute("INSERT INTO users(username,password_hash) VALUES('alice','test')")
        await connection.execute("INSERT INTO projects(user_id,name) VALUES(1,'images')")
        await connection.commit()
    service = HistoryService(repository)
    request = GenerateRequest(provider="compatible", model="test-model", prompt="test", project_id=1)
    history_id, batch_id, task_id = await service.create_generation(request, 1, include_batch_id=True, include_task_id=True)
    error = ProviderRequestError(status_code=422, request_id="req-42", response_content=b'{"error":{"code":"invalid_size","param":"size","message":"invalid pixels"}}')
    with pytest.raises(ProviderRequestError):
        await service.execute_generation(history_id, request, SimpleNamespace(generate=AsyncMock(side_effect=error)), 1,
                                         batch_id=batch_id, task_id=task_id, worker_id="test-worker")
    await initialize_database(db)  # Idempotent upgrade and restart preserve diagnostics.
    reopened = HistoryRepository(db)
    assert (await reopened.get(1, history_id)).batches[0].error_details == error.details
    assert (await reopened.get_generation_batch(1, history_id, batch_id)).error_details == error.details
    assert GenerationTaskDetail.model_validate(await reopened.get_generation_task(1, task_id)).error_details == error.details
    assert GenerationTaskDetail.model_validate((await reopened.list_generation_tasks(1))[0]).error_details == error.details
    assert await reopened.get_generation_task(2, task_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("stage,exception", [("query", httpx.ConnectError("connection refused")), ("storage", RuntimeError("R2 upload unavailable"))])
async def test_video_worker_saves_local_failure_stage_and_original_task_id(tmp_path, stage, exception):
    task = {"id": 1, "status": "running", "tracking_abandoned": 0, "upstream_task_id": "original-task",
            "upstream_status": "succeeded" if stage == "storage" else "running", "api_key_config_id": 1}
    repository = SimpleNamespace(database_path=tmp_path / "video.db", get_task=AsyncMock(return_value=task),
                                 get_key=AsyncMock(return_value={"api_key": "secret-key"}), update_task=AsyncMock())
    provider = SimpleNamespace(query=AsyncMock(side_effect=exception if stage == "query" else None,
                                              return_value={"status": "succeeded"}))
    service = VideoService(repository, Settings(_env_file=None), provider=provider, storage=SimpleNamespace(), probe=AsyncMock())
    service.save_results = AsyncMock(side_effect=exception)
    await service.run(1, 1)
    saved = repository.update_task.await_args.kwargs
    details = json.loads(saved["error_details_json"])
    assert details["stage"] == stage and details["upstream_task_id"] == "original-task"
    assert details["exception_type"] == type(exception).__name__
    assert saved["status"] == ("storage_failed" if stage == "storage" else "polling_paused")


@pytest.mark.asyncio
async def test_video_download_failure_is_distinguished_from_storage(tmp_path, monkeypatch):
    task = {"id": 1, "status": "running", "tracking_abandoned": 0, "upstream_task_id": "original-task",
            "upstream_status": "succeeded", "api_key_config_id": 1}
    repository = SimpleNamespace(database_path=tmp_path / "video.db", get_task=AsyncMock(return_value=task),
                                 get_key=AsyncMock(return_value={"api_key": "secret-key"}), update_task=AsyncMock(),
                                 result_for_position=AsyncMock(return_value={"id": 1, "stored": False}))
    provider = SimpleNamespace(query=AsyncMock(return_value={"status": "succeeded", "content": {"video_url": "https://cdn.example/result.mp4"}}))
    service = VideoService(repository, Settings(_env_file=None), provider=provider, storage=SimpleNamespace(), probe=AsyncMock())
    service.require_pipeline = AsyncMock()
    service.assets = SimpleNamespace(path=lambda relative: tmp_path / relative)
    monkeypatch.setattr("app.video.service.safe_download", AsyncMock(side_effect=httpx.ConnectError("Download connection refused")))
    await service.run(1, 1)
    saved = repository.update_task.await_args.kwargs
    assert json.loads(saved["error_details_json"])["stage"] == "download"
    assert saved["status"] == "storage_failed"


@pytest.mark.asyncio
async def test_video_uncertain_submission_keeps_http_reason_without_resubmitting():
    provider = VideoProvider(SimpleNamespace(video_api_base_url="https://relay.example", video_poll_interval=0.01),
                             httpx.MockTransport(lambda request: httpx.Response(503, json={"error": {"message": "upstream unavailable", "code": "busy"}})))
    from app.video.repository import VideoError
    with pytest.raises(VideoError) as caught:
        await provider.create("secret", {})
    assert caught.value.code == "video_submission_unknown"
    assert caught.value.details["http_status"] == 503
    assert caught.value.details["upstream_message"] == "upstream unavailable"
