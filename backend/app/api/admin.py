from fastapi import APIRouter, Depends, HTTPException, Response

from app.auth import hash_password
from app.dependencies import (
    get_admin_repository,
    get_current_admin,
    get_user_repository,
)
from app.repositories.admin_repository import AdminRepository
from app.repositories.user_repository import UserRepository
from app.schemas.admin import (
    AdminPasswordResetRequest,
    AdminUsageRecord,
    AdminUserSummary,
)
from app.schemas.auth import StoredSessionUser

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserSummary])
async def list_users(
    _: StoredSessionUser = Depends(get_current_admin),
    repository: AdminRepository = Depends(get_admin_repository),
) -> list[AdminUserSummary]:
    return await repository.list_users()


@router.get("/users/{user_id}/usage", response_model=list[AdminUsageRecord])
async def list_user_usage(
    user_id: int,
    _: StoredSessionUser = Depends(get_current_admin),
    repository: AdminRepository = Depends(get_admin_repository),
) -> list[AdminUsageRecord]:
    if await repository.get_user(user_id) is None:
        raise HTTPException(
            404,
            {"error": {"code": "user_not_found", "message": "用户不存在"}},
        )
    return await repository.list_usage(user_id)


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_user_password(
    user_id: int,
    request: AdminPasswordResetRequest,
    _: StoredSessionUser = Depends(get_current_admin),
    admin_repository: AdminRepository = Depends(get_admin_repository),
    user_repository: UserRepository = Depends(get_user_repository),
) -> Response:
    if await admin_repository.get_user(user_id) is None:
        raise HTTPException(
            404,
            {"error": {"code": "user_not_found", "message": "用户不存在"}},
        )
    await user_repository.update_password(user_id, hash_password(request.new_password))
    await user_repository.delete_sessions_for_user(user_id)
    return Response(status_code=204)
