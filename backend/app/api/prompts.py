from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.dependencies import get_current_user, get_prompt_repository
from app.repositories.prompt_repository import PromptNotFoundError, PromptRepository
from app.schemas.auth import StoredSessionUser
from app.schemas.prompt import PromptCreateRequest, PromptSummary, PromptUpdateRequest


router = APIRouter(prefix="/api/prompts", tags=["prompts"])


def prompt_error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": message}})


@router.get("", response_model=list[PromptSummary])
async def list_prompts(
    search: str = Query(default="", max_length=100),
    category: str = Query(default="", max_length=40),
    user: StoredSessionUser = Depends(get_current_user),
    repository: PromptRepository = Depends(get_prompt_repository),
) -> list[PromptSummary]:
    return await repository.list(user_id=user.id, search=search, category=category.strip())


@router.post("", response_model=PromptSummary, status_code=201)
async def create_prompt(
    request: PromptCreateRequest,
    user: StoredSessionUser = Depends(get_current_user),
    repository: PromptRepository = Depends(get_prompt_repository),
) -> PromptSummary:
    return await repository.create(user.id, request)


@router.get("/{prompt_id}", response_model=PromptSummary)
async def get_prompt(
    prompt_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: PromptRepository = Depends(get_prompt_repository),
) -> PromptSummary:
    try:
        return await repository.get(prompt_id, user_id=user.id)
    except PromptNotFoundError:
        raise prompt_error("prompt_not_found", "提示词不存在", 404) from None


@router.patch("/{prompt_id}", response_model=PromptSummary)
async def update_prompt(
    prompt_id: int,
    request: PromptUpdateRequest,
    user: StoredSessionUser = Depends(get_current_user),
    repository: PromptRepository = Depends(get_prompt_repository),
) -> PromptSummary:
    try:
        return await repository.update(prompt_id, user_id=user.id, request=request)
    except PromptNotFoundError:
        raise prompt_error("prompt_not_found", "提示词不存在", 404) from None


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: PromptRepository = Depends(get_prompt_repository),
) -> Response:
    try:
        await repository.delete(prompt_id, user_id=user.id)
    except PromptNotFoundError:
        raise prompt_error("prompt_not_found", "提示词不存在", 404) from None
    return Response(status_code=204)
