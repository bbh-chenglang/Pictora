from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_history_service, get_image_service
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.image_service import ImageService
from app.services.history_service import HistoryService
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/generate", tags=["generate"])


@router.post("", response_model=GenerateResponse)
async def generate_image(
    request: GenerateRequest,
    service: ImageService = Depends(get_image_service),
    history_service: HistoryService = Depends(get_history_service),
    user: StoredSessionUser = Depends(get_current_user),
) -> GenerateResponse:
    try:
        return await history_service.generate(request, service, user.id)
    except Exception as exc:
        from app.repositories.project_repository import ProjectNotFoundError
        if isinstance(exc, ProjectNotFoundError):
            from fastapi import HTTPException
            raise HTTPException(404, {"error": {"code": "project_not_found", "message": "项目不存在"}}) from None
        raise
