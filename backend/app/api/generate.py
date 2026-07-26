from fastapi import APIRouter, Depends

from app.dependencies import get_history_service, get_image_service
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.image_service import ImageService
from app.services.history_service import HistoryService

router = APIRouter(prefix="/api/generate", tags=["generate"])


@router.post("", response_model=GenerateResponse)
async def generate_image(
    request: GenerateRequest,
    service: ImageService = Depends(get_image_service),
    history_service: HistoryService = Depends(get_history_service),
) -> GenerateResponse:
    return await history_service.generate(request, service)
