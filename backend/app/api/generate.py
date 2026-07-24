from fastapi import APIRouter, Depends

from app.dependencies import get_image_service
from app.schemas.generate import GenerateRequest, GenerateResponse
from app.services.image_service import ImageService

router = APIRouter(prefix="/api/generate", tags=["generate"])


@router.post("", response_model=GenerateResponse)
async def generate_image(
    request: GenerateRequest,
    service: ImageService = Depends(get_image_service),
) -> GenerateResponse:
    return await service.generate(request)
