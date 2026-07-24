from fastapi import APIRouter, Depends

from app.dependencies import get_image_service
from app.services.image_service import ImageService

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("")
async def list_providers(service: ImageService = Depends(get_image_service)):
    return {"providers": await service.list_providers()}
