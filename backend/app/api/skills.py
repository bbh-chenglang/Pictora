import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from app.dependencies import get_current_admin, get_current_user, get_skill_repository
from app.repositories.skill_repository import SkillNotFoundError, SkillRepository, SkillStateError
from app.schemas.auth import StoredSessionUser
from app.schemas.skill import (
    SkillCategory,
    SkillCreateRequest,
    SkillReviewRequest,
    SkillSummary,
    SkillUseResponse,
)


router = APIRouter(prefix="/api/skills", tags=["skills"])
MAX_COVER_BYTES = 5 * 1024 * 1024
ALLOWED_COVER_TYPES = {"image/jpeg", "image/png", "image/webp"}


def skill_error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": message}})


@router.get("", response_model=list[SkillSummary])
async def list_skills(
    scope: str = Query(default="discover", pattern="^(discover|mine|favorites|review)$"),
    search: str = Query(default="", max_length=100),
    category: str = Query(default="", pattern="^(|portrait|product|marketing|illustration|other)$"),
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> list[SkillSummary]:
    if scope == "review" and not user.is_admin:
        raise skill_error("admin_required", "需要管理员权限", 403)
    return await repository.list(
        user_id=user.id, scope=scope, search=search, category=category
    )


@router.post("", response_model=SkillSummary, status_code=201)
async def create_skill(
    title: str = Form(...),
    description: str = Form(...),
    category: SkillCategory = Form(...),
    workflow_json: str = Form(...),
    cover: UploadFile | None = File(default=None),
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> SkillSummary:
    try:
        request = SkillCreateRequest(
            title=title,
            description=description,
            category=category,
            workflow=json.loads(workflow_json),
        )
    except (json.JSONDecodeError, ValidationError) as exc:
        raise skill_error("invalid_skill", "技能配置不完整或格式无效", 422) from exc

    cover_data: bytes | None = None
    cover_type: str | None = None
    if cover is not None:
        cover_type = cover.content_type or ""
        if cover_type not in ALLOWED_COVER_TYPES:
            raise skill_error("invalid_cover", "封面仅支持 JPG、PNG 或 WebP", 415)
        cover_data = await cover.read(MAX_COVER_BYTES + 1)
        if len(cover_data) > MAX_COVER_BYTES:
            raise skill_error("cover_too_large", "封面不能超过 5 MB", 413)
        if not cover_data:
            cover_type = None
            cover_data = None
    return await repository.create(
        user_id=user.id,
        request=request,
        cover_mime_type=cover_type,
        cover_data=cover_data,
    )


@router.get("/{skill_id}", response_model=SkillSummary)
async def get_skill(
    skill_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> SkillSummary:
    try:
        return await repository.get(skill_id, user_id=user.id, is_admin=user.is_admin)
    except SkillNotFoundError:
        raise skill_error("skill_not_found", "技能不存在", 404) from None


@router.get("/{skill_id}/cover")
async def get_skill_cover(
    skill_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> Response:
    try:
        mime_type, data = await repository.cover(
            skill_id, user_id=user.id, is_admin=user.is_admin
        )
    except SkillNotFoundError:
        raise skill_error("skill_cover_not_found", "技能封面不存在", 404) from None
    return Response(data, media_type=mime_type, headers={"Cache-Control": "private, max-age=3600"})


@router.post("/{skill_id}/submit", response_model=SkillSummary)
async def submit_skill(
    skill_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> SkillSummary:
    try:
        return await repository.submit(skill_id, user_id=user.id)
    except SkillStateError as exc:
        raise skill_error("invalid_skill_state", str(exc), 409) from None


@router.post("/{skill_id}/review", response_model=SkillSummary)
async def review_skill(
    skill_id: int,
    request: SkillReviewRequest,
    admin: StoredSessionUser = Depends(get_current_admin),
    repository: SkillRepository = Depends(get_skill_repository),
) -> SkillSummary:
    try:
        return await repository.review(
            skill_id,
            decision=request.decision,
            note=request.note,
            admin_id=admin.id,
        )
    except SkillStateError as exc:
        raise skill_error("invalid_skill_state", str(exc), 409) from None


@router.put("/{skill_id}/favorite", response_model=SkillSummary)
async def favorite_skill(
    skill_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> SkillSummary:
    try:
        return await repository.set_favorite(skill_id, user_id=user.id, favorite=True)
    except SkillNotFoundError:
        raise skill_error("skill_not_found", "技能不存在", 404) from None


@router.delete("/{skill_id}/favorite", response_model=SkillSummary)
async def unfavorite_skill(
    skill_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> SkillSummary:
    try:
        return await repository.set_favorite(skill_id, user_id=user.id, favorite=False)
    except SkillNotFoundError:
        raise skill_error("skill_not_found", "技能不存在", 404) from None


@router.post("/{skill_id}/use", response_model=SkillUseResponse)
async def use_skill(
    skill_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> SkillUseResponse:
    try:
        skill = await repository.record_use(skill_id, user_id=user.id)
    except SkillNotFoundError:
        raise skill_error("skill_not_found", "技能不存在", 404) from None
    return SkillUseResponse(skill=skill, workflow=skill.workflow)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: SkillRepository = Depends(get_skill_repository),
) -> Response:
    try:
        await repository.delete(skill_id, user_id=user.id, is_admin=user.is_admin)
    except SkillStateError as exc:
        raise skill_error("invalid_skill_state", str(exc), 409) from None
    return Response(status_code=204)
