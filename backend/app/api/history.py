from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.concurrency import run_in_threadpool

from app.dependencies import get_current_user, get_history_repository
from app.image_thumbnails import ThumbnailGenerationError, create_webp_thumbnail
from app.repositories.history_repository import HistoryRepository
from app.schemas.history import GenerationBatchDetail, HistoryDetail, HistoryImageEditSnapshot, HistorySummary
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/history", tags=["history"])

HISTORY_IMAGE_CACHE_CONTROL = "private, max-age=31536000, immutable"


def _history_image_headers(
    history_id: int,
    image_id: int,
    *,
    variant: str = "original",
) -> dict[str, str]:
    variant_suffix = "" if variant == "original" else f"-{variant}"
    return {
        "Cache-Control": HISTORY_IMAGE_CACHE_CONTROL,
        "ETag": f'"history-{history_id}-image-{image_id}{variant_suffix}"',
        "Vary": "Cookie",
    }


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    if not if_none_match:
        return False
    normalized_etag = etag.removeprefix("W/")
    return any(
        candidate == "*" or candidate.removeprefix("W/") == normalized_etag
        for candidate in (value.strip() for value in if_none_match.split(","))
    )


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
    request: Request,
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
    headers = _history_image_headers(history_id, image_id)
    if _etag_matches(request.headers.get("if-none-match"), headers["ETag"]):
        return Response(status_code=304, headers=headers)
    return Response(
        content=image.data,
        media_type=image.mime_type,
        headers=headers,
    )


@router.get("/{history_id}/images/{image_id}/thumbnail")
async def read_history_image_thumbnail(
    history_id: int,
    image_id: int,
    request: Request,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> Response:
    thumbnail = await repository.get_image_thumbnail(user.id, history_id, image_id)
    if thumbnail is None:
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
        try:
            generated = await run_in_threadpool(create_webp_thumbnail, image.data)
        except ThumbnailGenerationError as exc:
            raise HTTPException(
                422,
                {
                    "error": {
                        "code": "history_image_thumbnail_failed",
                        "message": "无法生成图片缩略图",
                    }
                },
            ) from exc
        await repository.save_image_thumbnail(
            user_id=user.id,
            history_id=history_id,
            image_id=image_id,
            mime_type="image/webp",
            width=generated.width,
            height=generated.height,
            data=generated.data,
        )
        content = generated.data
        media_type = "image/webp"
    else:
        content = thumbnail.data
        media_type = thumbnail.mime_type

    headers = _history_image_headers(history_id, image_id, variant="thumbnail-v1")
    if _etag_matches(request.headers.get("if-none-match"), headers["ETag"]):
        return Response(status_code=304, headers=headers)
    return Response(content=content, media_type=media_type, headers=headers)


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


@router.delete("/{history_id}/batches/{batch_id}/slots/{position}", status_code=204)
async def delete_history_generation_slot(
    history_id: int,
    batch_id: int,
    position: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> Response:
    deleted = await repository.delete_generation_slot(
        user.id,
        history_id,
        batch_id,
        position,
    )
    if not deleted:
        raise HTTPException(
            404,
            {
                "error": {
                    "code": "generation_slot_not_found",
                    "message": "生成卡片不存在",
                }
            },
        )
    return Response(status_code=204)


@router.post("/{history_id}/batches/{batch_id}/slots/{position}/cancel", status_code=204)
async def cancel_history_generation_slot(
    history_id: int,
    batch_id: int,
    position: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> Response:
    cancelled = await repository.cancel_generation_slot(
        user.id,
        history_id,
        batch_id,
        position,
    )
    if not cancelled:
        raise HTTPException(
            409,
            {
                "error": {
                    "code": "generation_slot_not_cancellable",
                    "message": "该图片已经结束或不存在",
                }
            },
        )
    return Response(status_code=204)
