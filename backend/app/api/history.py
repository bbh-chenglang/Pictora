from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import get_current_user, get_history_repository
from app.repositories.history_repository import HistoryRepository
from app.schemas.history import GenerationBatchDetail, HistoryDetail, HistoryImageEditSnapshot, HistorySummary
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=list[HistorySummary])
async def list_history(
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> list[HistorySummary]:
    return await repository.list(user_id=user.id, limit=50)


@router.get("/{history_id}", response_model=HistoryDetail)
async def read_history(
    history_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> HistoryDetail:
    record = await repository.get(user.id, history_id)
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


@router.get("/{history_id}/batches/{batch_id}", response_model=GenerationBatchDetail)
async def read_generation_batch(
    history_id: int,
    batch_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> GenerationBatchDetail:
    batch = await repository.get_generation_batch(user.id, history_id, batch_id)
    if batch is None:
        raise HTTPException(
            404,
            {"error": {"code": "generation_batch_not_found", "message": "生成批次不存在"}},
        )
    return batch


@router.get("/{history_id}/images/{image_id}")
async def read_history_image(
    history_id: int,
    image_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> Response:
    image = await repository.get_image(user.id, history_id, image_id)
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
    return Response(
        content=image.data,
        media_type=image.mime_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get(
    "/{history_id}/images/{image_id}/edit",
    response_model=HistoryImageEditSnapshot,
)
async def read_history_image_edit_snapshot(
    history_id: int,
    image_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> HistoryImageEditSnapshot:
    snapshot = await repository.get_image_edit_snapshot(user.id, history_id, image_id)
    if snapshot is None:
        raise HTTPException(
            404,
            {
                "error": {
                    "code": "history_image_not_found",
                    "message": "历史图片不存在",
                }
            },
        )
    return snapshot


@router.delete("/{history_id}/images/{image_id}", status_code=204)
async def delete_history_image(
    history_id: int,
    image_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> Response:
    deleted = await repository.delete_generated_image(user.id, history_id, image_id)
    if not deleted:
        raise HTTPException(
            404,
            {
                "error": {
                    "code": "history_image_not_found",
                    "message": "历史图片不存在",
                }
            },
        )
    return Response(status_code=204)
