from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import get_current_user, get_history_service, get_image_service
from app.schemas.analyze import AnalyzeResponse
from app.schemas.generate import ReferenceImage
from app.services.image_service import ImageService
from app.services.history_service import HistoryService
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/analyze", tags=["analyze"])
SUPPORTED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_REFERENCE_IMAGES = 8
Detail = Literal["low", "medium", "high", "original", "auto"]


@router.post("", response_model=AnalyzeResponse)
async def analyze_image(
    provider: Annotated[str, Form()],
    model: Annotated[str, Form()],
    api_key_config_id: Annotated[int | None, Form()] = None,
    project_id: Annotated[int | None, Form()] = None,
    prompt: Annotated[str, Form()] = "Describe this image",
    detail: Annotated[Detail, Form()] = "auto",
    image: Annotated[UploadFile | None, File()] = None,
    images: Annotated[list[UploadFile] | None, File()] = None,
    service: ImageService = Depends(get_image_service),
    history_service: HistoryService = Depends(get_history_service),
    user: StoredSessionUser = Depends(get_current_user),
) -> AnalyzeResponse:
    uploads = ([image] if image is not None else []) + (images or [])
    if not uploads:
        raise HTTPException(400, {"error": {"code": "invalid_image", "message": "At least one image is required"}})
    if len(uploads) > MAX_REFERENCE_IMAGES:
        raise HTTPException(
            400,
            {"error": {"code": "invalid_image", "message": f"At most {MAX_REFERENCE_IMAGES} images are allowed"}},
        )
    reference_images: list[ReferenceImage] = []
    for upload in uploads:
        if upload.content_type not in SUPPORTED_TYPES:
            raise HTTPException(400, {"error": {"code": "invalid_image", "message": "Unsupported image type"}})
        image_bytes = await upload.read()
        if not image_bytes:
            raise HTTPException(400, {"error": {"code": "invalid_image", "message": "Image file is empty"}})
        reference_images.append(
            ReferenceImage(
                data=image_bytes,
                content_type=upload.content_type or "application/octet-stream",
                filename=upload.filename,
            )
        )
    primary_image = reference_images[0]
    analyze_kwargs = dict(
        user_id=user.id,
        image_service=service,
        provider=provider,
        model=model,
        prompt=prompt,
        detail=detail,
        image_bytes=primary_image.data,
        content_type=primary_image.content_type,
        filename=primary_image.filename,
    )
    if len(reference_images) > 1:
        analyze_kwargs["reference_images"] = reference_images
    if project_id is not None:
        analyze_kwargs["project_id"] = project_id
    if api_key_config_id is not None:
        analyze_kwargs["api_key_config_id"] = api_key_config_id
    try:
        return await history_service.analyze(**analyze_kwargs)
    except Exception as exc:
        from app.repositories.api_key_config_repository import ApiKeyConfigNotFoundError
        from app.repositories.project_repository import ProjectNotFoundError
        if isinstance(exc, ProjectNotFoundError):
            raise HTTPException(404, {"error": {"code": "project_not_found", "message": "项目不存在"}}) from None
        if isinstance(exc, ApiKeyConfigNotFoundError):
            raise HTTPException(404, {"error": {"code": "api_key_config_not_found", "message": "配置不存在"}}) from None
        raise
