from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.dependencies import get_current_user, get_history_service, get_image_service
from app.schemas.analyze import AnalyzeResponse
from app.services.image_service import ImageService
from app.services.history_service import HistoryService
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/analyze", tags=["analyze"])
SUPPORTED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
Detail = Literal["low", "high", "original", "auto"]


@router.post("", response_model=AnalyzeResponse)
async def analyze_image(
    provider: Annotated[str, Form()],
    model: Annotated[str, Form()],
    project_id: Annotated[int | None, Form()] = None,
    prompt: Annotated[str, Form()] = "Describe this image",
    detail: Annotated[Detail, Form()] = "auto",
    image: UploadFile = File(...),
    service: ImageService = Depends(get_image_service),
    history_service: HistoryService = Depends(get_history_service),
    user: StoredSessionUser = Depends(get_current_user),
) -> AnalyzeResponse:
    if image.content_type not in SUPPORTED_TYPES:
        raise HTTPException(400, {"error": {"code": "invalid_image", "message": "Unsupported image type"}})
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(400, {"error": {"code": "invalid_image", "message": "Image file is empty"}})
    analyze_kwargs = dict(
        user_id=user.id,
        image_service=service,
        provider=provider,
        model=model,
        prompt=prompt,
        detail=detail,
        image_bytes=image_bytes,
        content_type=image.content_type or "application/octet-stream",
        filename=image.filename,
    )
    if project_id is not None:
        analyze_kwargs["project_id"] = project_id
    try:
        return await history_service.analyze(**analyze_kwargs)
    except Exception as exc:
        from app.repositories.project_repository import ProjectNotFoundError
        if isinstance(exc, ProjectNotFoundError):
            raise HTTPException(404, {"error": {"code": "project_not_found", "message": "项目不存在"}}) from None
        raise
