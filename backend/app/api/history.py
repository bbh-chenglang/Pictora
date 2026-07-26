from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import get_history_repository
from app.repositories.history_repository import HistoryRepository
from app.schemas.history import HistoryDetail, HistorySummary

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistorySummary])
async def list_history(
    repository: HistoryRepository = Depends(get_history_repository),
) -> list[HistorySummary]:
    return await repository.list(limit=50)


@router.get("/{history_id}", response_model=HistoryDetail)
async def read_history(
    history_id: int,
    repository: HistoryRepository = Depends(get_history_repository),
) -> HistoryDetail:
    record = await repository.get(history_id)
    if record is None:
        raise HTTPException(
            404,
            {
                "error": {
                    "code": "history_not_found",
                    "message": "历史记录不存在",
                }
            },
        )
    return record


@router.get("/{history_id}/images/{image_id}")
async def read_history_image(
    history_id: int,
    image_id: int,
    repository: HistoryRepository = Depends(get_history_repository),
) -> Response:
    image = await repository.get_image(history_id, image_id)
    if image is None:
        raise HTTPException(
            404,
            {
                "error": {
                    "code": "history_image_not_found",
                    "message": "历史图片不存在",
                }
            },
        )
    return Response(content=image.data, media_type=image.mime_type)
