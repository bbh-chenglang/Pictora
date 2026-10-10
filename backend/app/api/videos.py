"""Independent video settings, signed references and durable asynchronous tasks."""
import asyncio
import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from starlette.requests import Request

from app.dependencies import get_current_user, get_history_repository, get_video_service
from app.schemas.auth import StoredSessionUser
from app.video.repository import VideoError
from app.video.schemas import (
    BindUpstreamTask, HistoryImageSource, VideoKeyCreate, VideoKeySelection,
    VideoKeyUpdate, VideoTaskCreate,
)
from app.video.service import VideoService

router = APIRouter(prefix="/api/videos", tags=["videos"])
settings_router = APIRouter(prefix="/api/settings/video-api-keys", tags=["video-settings"])


def public_asset(asset):
    return {k: v for k, v in asset.items() if k not in ("relative_path", "user_id")} | {
        "preview_url": f"/api/videos/assets/{asset['id']}/file"
    }


@settings_router.get("")
async def list_keys(user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    return await service.repository.list_keys(user.id)


@settings_router.post("", status_code=201)
async def create_key(body: VideoKeyCreate, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    if not any(model['id'] == body.model for model in await service.catalog.get(body.api_key.get_secret_value(), force=True)):
        raise VideoError("video_model_unsupported", "视频模型未开放", 422)
    return await service.repository.save_key(user.id, body.alias, body.api_key.get_secret_value(), body.model)


@settings_router.put("/active")
async def select_key(body: VideoKeySelection, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    await service.repository.activate_key(user.id, body.config_id)
    return await service.repository.list_keys(user.id)


@settings_router.patch("/{config_id}")
async def update_key(config_id: int, body: VideoKeyUpdate, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    current = await service.repository.get_key(user.id, config_id)
    model = body.model or current["model"]
    if model != current['model'] and not any(item['id'] == model for item in await service.catalog.get(current['api_key'], force=True)):
        raise VideoError("video_model_unsupported", "视频模型未开放", 422)
    return await service.repository.save_key(user.id, body.alias or current["alias"], body.api_key.get_secret_value() if body.api_key else None, model, config_id)


@settings_router.delete("/{config_id}", status_code=204)
async def delete_key(config_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    await service.repository.delete_key(user.id, config_id)


@settings_router.post("/{config_id}/test")
async def test_key(config_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    config = await service.repository.get_key(user.id, config_id)
    result = await service.provider.test_key(config["api_key"])
    return result


@router.get("/readiness")
async def readiness(user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    return await service.features()


@router.get("/models")
async def models(refresh: bool = Query(False), user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    keys = await service.repository.list_keys(user.id)
    active = next((item for item in keys['configs'] if item['id'] == keys['active_config_id']), None)
    key = (await service.repository.get_key(user.id, active['id']))['api_key'] if active else None
    catalog = await service.catalog.get(key, force=refresh and service.provider_error is None)
    return {"models": catalog, "features": await service.features()}


@router.post("/assets/upload", status_code=201)
async def upload_asset(type: Literal["image", "video", "audio"] = Query(...), file: UploadFile = File(...), name: str = Form("", max_length=80), user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    try:
        return public_asset(await service.assets.ingest(user.id, type, file, name))
    finally:
        await file.close()


@router.post("/assets/from-history", status_code=201)
async def history_asset(body: HistoryImageSource, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service), history=Depends(get_history_repository)):
    return public_asset(await service.history_image(user.id, history, body.history_id, body.image_id, body.name))


@router.get("/assets/public/{asset_id}")
async def public_asset_file(asset_id: str, expires: int, signature: str = Query(..., max_length=64), service: VideoService = Depends(get_video_service)):
    service.assets.verify_signature(asset_id, expires, signature)
    asset = await service.repository.get_asset(asset_id)
    file = service.assets.path(asset["relative_path"])
    if not file.is_file():
        raise VideoError("video_asset_missing", "素材已不可用", 404)
    return FileResponse(file, media_type=asset["mime_type"], headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"})


@router.get("/assets/{asset_id}/file")
async def asset_file(asset_id: str, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    asset = await service.repository.get_asset(asset_id, user.id)
    file = service.assets.path(asset["relative_path"])
    if not file.is_file():
        raise VideoError("video_asset_missing", "素材已不可用", 404)
    return FileResponse(file, media_type=asset["mime_type"], headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/tasks", status_code=202)
async def create_task(body: VideoTaskCreate, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    task = await service.create(user.id, body)
    return {"task_id": task["id"], "status_url": f"/api/videos/tasks/{task['id']}", "task": task}


@router.get("/tasks")
async def list_tasks(project_id: int | None = Query(None, gt=0), limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0), user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    return await service.repository.list_tasks(user.id, project_id, limit=limit, offset=offset)


@router.get("/tasks/{task_id}")
async def task_detail(task_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    return await service.repository.get_task(user.id, task_id, public=True)


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    return await service.resume(user.id, task_id)


@router.post("/tasks/{task_id}/retry-save")
async def retry_save(task_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    task = await service.repository.get_task(user.id, task_id)
    if task["status"] != "storage_failed" or task["upstream_status"] not in ("succeeded", "completed"):
        raise VideoError("video_save_invalid", "只有已生成但保存失败的任务可以重试保存", 409)
    return await service.resume(user.id, task_id)


@router.post("/tasks/{task_id}/bind")
async def bind_task(task_id: int, body: BindUpstreamTask, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    return await service.bind(user.id, task_id, body.upstream_task_id.strip())


@router.post("/tasks/{task_id}/abandon")
async def abandon_task(task_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    return await service.abandon(user.id, task_id)


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    await service.repository.delete_task(user.id, task_id)
    await service.assets.cleanup_deleted_references()


async def owned_result(service, user_id, task_id, result_id):
    task = await service.repository.get_task(user_id, task_id)
    result = next((r for r in task["results"] if r["id"] == result_id and r["stored"]), None)
    if result is None:
        raise VideoError("video_result_not_found", "已保存的视频结果不存在", 404)
    return result


@router.get("/tasks/{task_id}/results/{result_id}/play")
async def play(task_id: int, result_id: int, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    result = await owned_result(service, user.id, task_id, result_id)
    try:
        url = service.storage.playback_url(result["object_key"])
    except Exception:
        raise VideoError("video_storage_unavailable", "视频播放暂不可用，请稍后重试", 503) from None
    return RedirectResponse(url, status_code=307, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


class VideoDownloadResponse(StreamingResponse):
    """Close the SDK body even if disconnect happens before iteration starts."""
    def __init__(self, content, body, **kwargs):
        self.storage_body = body
        super().__init__(content, **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await asyncio.to_thread(self.storage_body.close)


@router.get("/tasks/{task_id}/results/{result_id}/download")
async def download(task_id: int, result_id: int, request: Request, user: StoredSessionUser = Depends(get_current_user), service: VideoService = Depends(get_video_service)):
    result = await owned_result(service, user.id, task_id, result_id)
    range_header = request.headers.get("range")
    if range_header and (not re.fullmatch(r"bytes=(?:[0-9]+-[0-9]*|-[0-9]+)", range_header) or len(range_header) > 80):
        raise VideoError("video_range_invalid", "只支持单段字节范围", 416)
    try:
        response = await service.storage.open_download(result["object_key"], range_header)
    except Exception as exc:
        error = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error == "InvalidRange":
            raise VideoError("video_range_invalid", "请求范围超出视频大小", 416) from None
        raise VideoError("video_storage_unavailable", "视频下载暂不可用，请稍后重试", 503) from None
    body = response["Body"]
    async def chunks():
        try:
            while chunk := await asyncio.to_thread(body.read, 64 * 1024):
                yield chunk
        finally:
            await asyncio.to_thread(body.close)
    headers = {"Content-Disposition": "attachment; filename*=UTF-8''" + quote(result["filename"], safe=""), "Cache-Control": "private, no-store", "Accept-Ranges": "bytes", "X-Content-Type-Options": "nosniff"}
    if response.get("ContentLength") is not None:
        headers["Content-Length"] = str(response["ContentLength"])
    if response.get("ContentRange"):
        headers["Content-Range"] = response["ContentRange"]
    return VideoDownloadResponse(chunks(), body, status_code=206 if response.get("ContentRange") else 200, media_type="video/mp4", headers=headers)
