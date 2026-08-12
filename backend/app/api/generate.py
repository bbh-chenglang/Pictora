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
from app.repositories.history_repository import (
    HistoryConversationBusyError,
    HistoryConversationNotFoundError,
    HistoryRepository,
)
from app.schemas.auth import StoredSessionUser
from app.schemas.generate import (
    CancelGenerationResponse,
    GenerateRequest,
    GenerateTaskResponse,
    ReferenceImage,
    ReferenceImageInput,
)
from app.schemas.history import ReferenceCategory
from app.services.generation_task_manager import GenerationTaskManager
from app.services.history_service import HistoryService
from app.services.image_service import ImageService

router = APIRouter(prefix="/api/generate", tags=["generate"])
logger = logging.getLogger(__name__)
SUPPORTED_REFERENCE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_GPT_REFERENCE_IMAGES = 16
MAX_GEMINI_REFERENCE_IMAGES = 14
MAX_LEGACY_GEMINI_REFERENCE_IMAGES = 3
MAX_GROK_REFERENCE_IMAGES = 3
Detail = Literal["low", "medium", "high", "original", "auto"]
AspectRatio = Literal[
    "auto", "1:1", "1:2", "1:4", "1:8", "2:1", "2:3", "3:2", "3:4",
    "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "19.5:9",
    "9:19.5", "20:9", "9:20", "21:9",
]
Resolution = Literal["1K", "2K", "4K"]
OutputFormat = Literal["png", "jpeg", "webp"]
Background = Literal["auto", "opaque", "transparent"]
Moderation = Literal["auto", "low"]


def _reference_limit(provider: str, model: str) -> int:
    if provider == "grok":
        return MAX_GROK_REFERENCE_IMAGES
    if provider == "gemini":
        return (
            MAX_GEMINI_REFERENCE_IMAGES
            if "gemini-3" in model.casefold()
            else MAX_LEGACY_GEMINI_REFERENCE_IMAGES
        )
    return MAX_GPT_REFERENCE_IMAGES


async def _execute_generation_task(
    history_id: int,
    batch_id: int,
    request: GenerateRequest,
    service: ImageService,
    history_service: HistoryService,
    user: StoredSessionUser,
    reference_image: ReferenceImageInput | None = None,
) -> None:
    try:
        await history_service.execute_generation(
            history_id,
            request,
            service,
            user.id,
            reference_image=reference_image,
            batch_id=batch_id,
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
    reference_image: ReferenceImageInput | None = None,
) -> GenerateTaskResponse:
    try:
        history_id, batch_id = await history_service.create_generation(
            request,
            user.id,
            reference_image=reference_image,
            include_batch_id=True,
        )
    except Exception as exc:
        from app.repositories.project_repository import ProjectNotFoundError

        if isinstance(exc, ProjectNotFoundError):
            raise HTTPException(404, {"error": {"code": "project_not_found", "message": "项目不存在"}}) from None
        if isinstance(exc, ApiKeyConfigNotFoundError):
            raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}}) from None
        if isinstance(exc, HistoryConversationNotFoundError):
            raise HTTPException(404, {"error": {"code": "conversation_not_found", "message": "当前对话不存在"}}) from None
        if isinstance(exc, HistoryConversationBusyError):
            raise HTTPException(409, {"error": {"code": "conversation_busy", "message": "当前对话仍在生成中"}}) from None
        raise
    task_manager.start(
        history_id,
        lambda: _execute_generation_task(
            history_id,
            batch_id,
            request,
            service,
            history_service,
            user,
            reference_image,
        ),
    )
    return GenerateTaskResponse(
        task_id=history_id,
        batch_id=batch_id,
        status_url=f"/api/history/{history_id}/batches/{batch_id}",
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
    image: Annotated[UploadFile | None, File()] = None,
    images: Annotated[list[UploadFile] | None, File()] = None,
    api_key_config_id: Annotated[int | None, Form(gt=0)] = None,
    project_id: Annotated[int | None, Form(gt=0)] = None,
    conversation_id: Annotated[int | None, Form(gt=0)] = None,
    image_categories: Annotated[list[ReferenceCategory] | None, Form()] = None,
    prompts: Annotated[list[str] | None, Form()] = None,
    count: Annotated[int, Form(ge=1, le=10)] = 1,
    detail: Annotated[Detail, Form()] = "auto",
    size: Annotated[str | None, Form()] = None,
    aspect_ratio: Annotated[AspectRatio | None, Form()] = None,
    resolution: Annotated[Resolution | None, Form()] = None,
    output_format: Annotated[OutputFormat | None, Form()] = None,
    background: Annotated[Background | None, Form()] = None,
    output_compression: Annotated[int | None, Form(ge=0, le=100)] = None,
    moderation: Annotated[Moderation | None, Form()] = None,
    service: ImageService = Depends(get_image_service),
    history_service: HistoryService = Depends(get_history_service),
    task_manager: GenerationTaskManager = Depends(get_generation_task_manager),
    user: StoredSessionUser = Depends(get_current_user),
) -> GenerateTaskResponse:
    uploads = ([image] if image is not None else []) + (images or [])
    if not uploads:
        raise HTTPException(
            400,
            {"error": {"code": "invalid_image", "message": "At least one image is required"}},
        )
    reference_limit = _reference_limit(provider, model)
    if len(uploads) > reference_limit:
        raise HTTPException(
            400,
            {"error": {"code": "invalid_image", "message": f"At most {reference_limit} images are allowed"}},
        )

    reference_images: list[ReferenceImage] = []
    for index, upload in enumerate(uploads):
        if upload.content_type not in SUPPORTED_REFERENCE_TYPES:
            raise HTTPException(
                400,
                {"error": {"code": "invalid_image", "message": "Unsupported image type"}},
            )
        image_bytes = await upload.read()
        if not image_bytes:
            raise HTTPException(
                400,
                {"error": {"code": "invalid_image", "message": "Image file is empty"}},
            )
        reference_images.append(
            ReferenceImage(
                data=image_bytes,
                content_type=upload.content_type or "application/octet-stream",
                filename=upload.filename,
                category=(image_categories or [])[index]
                if index < len(image_categories or [])
                else "person",
            )
        )
    request = GenerateRequest(
        provider=provider,
        model=model,
        api_key_config_id=api_key_config_id,
        project_id=project_id,
        conversation_id=conversation_id,
        prompt=prompt,
        prompts=prompts,
        count=count,
        detail=detail,
        size=size,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        output_format=output_format,
        background=background,
        output_compression=output_compression,
        moderation=moderation,
    )
    reference_image: ReferenceImageInput = (
        reference_images[0] if len(reference_images) == 1 else reference_images
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
