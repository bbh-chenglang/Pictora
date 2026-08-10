import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import (
    get_current_user,
    get_generation_task_manager,
    get_history_repository,
    get_history_service,
    get_image_service,
)
from app.repositories.api_key_config_repository import ApiKeyConfigNotFoundError
from app.repositories.history_repository import HistoryRepository
from app.schemas.auth import StoredSessionUser
from app.schemas.generate import (
    CancelGenerationResponse,
    GenerateRequest,
    GenerateTaskResponse,
    ReferenceImage,
)
from app.services.generation_task_manager import GenerationTaskManager
from app.services.history_service import HistoryService
from app.services.image_service import ImageService

router = APIRouter(prefix="/api/generate", tags=["generate"])
logger = logging.getLogger(__name__)
SUPPORTED_REFERENCE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
Detail = Literal["low", "medium", "high", "original", "auto"]
AspectRatio = Literal["1:1", "3:2", "2:3", "9:16", "16:9"]
Resolution = Literal["1K", "2K", "4K"]


async def _execute_generation_task(
    history_id: int,
    request: GenerateRequest,
    service: ImageService,
    history_service: HistoryService,
    user: StoredSessionUser,
    reference_image: ReferenceImage | None = None,
) -> None:
    try:
        await history_service.execute_generation(
            history_id,
            request,
            service,
            user.id,
            reference_image=reference_image,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Background image generation failed task_id=%d", history_id)


async def _submit_generation(
    request: GenerateRequest,
    service: ImageService,
    history_service: HistoryService,
    task_manager: GenerationTaskManager,
    user: StoredSessionUser,
    reference_image: ReferenceImage | None = None,
) -> GenerateTaskResponse:
    try:
        history_id = await history_service.create_generation(
            request,
            user.id,
            reference_image=reference_image,
        )
    except Exception as exc:
        from app.repositories.project_repository import ProjectNotFoundError

        if isinstance(exc, ProjectNotFoundError):
            raise HTTPException(404, {"error": {"code": "project_not_found", "message": "项目不存在"}}) from None
        if isinstance(exc, ApiKeyConfigNotFoundError):
            raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}}) from None
        raise
    task_manager.start(
        history_id,
        lambda: _execute_generation_task(
            history_id,
            request,
            service,
            history_service,
            user,
            reference_image,
        ),
    )
    return GenerateTaskResponse(
        task_id=history_id,
        status_url=f"/api/history/{history_id}",
    )


@router.post("", response_model=GenerateTaskResponse, status_code=202)
async def generate_image(
    request: GenerateRequest,
    service: ImageService = Depends(get_image_service),
    history_service: HistoryService = Depends(get_history_service),
    task_manager: GenerationTaskManager = Depends(get_generation_task_manager),
    user: StoredSessionUser = Depends(get_current_user),
) -> GenerateTaskResponse:
    return await _submit_generation(request, service, history_service, task_manager, user)


@router.post("/reference", response_model=GenerateTaskResponse, status_code=202)
async def generate_image_from_reference(
    provider: Annotated[str, Form()],
    model: Annotated[str, Form()],
    prompt: Annotated[str, Form(min_length=1, max_length=4000)],
    image: UploadFile = File(...),
    api_key_config_id: Annotated[int | None, Form(gt=0)] = None,
    project_id: Annotated[int | None, Form(gt=0)] = None,
    prompts: Annotated[list[str] | None, Form()] = None,
    count: Annotated[int, Form(ge=1, le=4)] = 1,
    detail: Annotated[Detail, Form()] = "auto",
    size: Annotated[str, Form()] = "1024x1024",
    aspect_ratio: Annotated[AspectRatio | None, Form()] = None,
    resolution: Annotated[Resolution | None, Form()] = None,
    service: ImageService = Depends(get_image_service),
    history_service: HistoryService = Depends(get_history_service),
    task_manager: GenerationTaskManager = Depends(get_generation_task_manager),
    user: StoredSessionUser = Depends(get_current_user),
) -> GenerateTaskResponse:
    if image.content_type not in SUPPORTED_REFERENCE_TYPES:
        raise HTTPException(
            400,
            {"error": {"code": "invalid_image", "message": "Unsupported image type"}},
        )
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(
            400,
            {"error": {"code": "invalid_image", "message": "Image file is empty"}},
        )
    request = GenerateRequest(
        provider=provider,
        model=model,
        api_key_config_id=api_key_config_id,
        project_id=project_id,
        prompt=prompt,
        prompts=prompts,
        count=count,
        detail=detail,
        size=size,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
    )
    reference_image = ReferenceImage(
        data=image_bytes,
        content_type=image.content_type or "application/octet-stream",
        filename=image.filename,
    )
    return await _submit_generation(
        request,
        service,
        history_service,
        task_manager,
        user,
        reference_image,
    )


@router.delete("/{task_id}", response_model=CancelGenerationResponse)
async def cancel_generation(
    task_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
    history_service: HistoryService = Depends(get_history_service),
    task_manager: GenerationTaskManager = Depends(get_generation_task_manager),
) -> CancelGenerationResponse:
    record = await repository.get(user.id, task_id)
    if record is None or record.kind != "generate":
        raise HTTPException(
            404,
            {"error": {"code": "generation_task_not_found", "message": "生成任务不存在"}},
        )
    if record.status != "pending":
        raise HTTPException(
            409,
            {"error": {"code": "generation_task_finished", "message": "生成任务已经结束"}},
        )
    await task_manager.cancel(task_id)
    await history_service.cancel_generation(task_id)
    return CancelGenerationResponse(task_id=task_id)
