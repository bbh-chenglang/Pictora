from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user, get_project_repository
from app.repositories.project_repository import (
    ProjectNameTakenError,
    ProjectNotFoundError,
    ProjectRepository,
)
from app.schemas.auth import StoredSessionUser
from app.schemas.project import (
    HistoryDeleteRequest,
    Project,
    ProjectCreateRequest,
    ProjectDeleteResult,
    ProjectRenameRequest,
    ProjectSummary,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


def project_error(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status, {"error": {"code": code, "message": message}})


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    user: StoredSessionUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_project_repository),
) -> list[ProjectSummary]:
    return await repository.list_with_history(user.id)


@router.post("", response_model=Project, status_code=201)
async def create_project(
    request: ProjectCreateRequest,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_project_repository),
) -> Project:
    try:
        return await repository.create(user.id, request.name)
    except ProjectNameTakenError:
        raise project_error("project_name_taken", "项目名称已存在", 409) from None


@router.patch("/{project_id}", response_model=Project)
async def rename_project(
    project_id: int,
    request: ProjectRenameRequest,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_project_repository),
) -> Project:
    try:
        return await repository.rename(project_id, user.id, request.name)
    except ProjectNotFoundError:
        raise project_error("project_not_found", "项目不存在", 404) from None
    except ProjectNameTakenError:
        raise project_error("project_name_taken", "项目名称已存在", 409) from None


@router.delete("/{project_id}", response_model=ProjectDeleteResult)
async def delete_project(
    project_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_project_repository),
) -> ProjectDeleteResult:
    try:
        return await repository.delete(project_id, user.id)
    except ProjectNotFoundError:
        raise project_error("project_not_found", "项目不存在", 404) from None


@router.delete("/{project_id}/history")
async def delete_project_history(
    project_id: int,
    request: HistoryDeleteRequest,
    user: StoredSessionUser = Depends(get_current_user),
    repository: ProjectRepository = Depends(get_project_repository),
) -> dict[str, int]:
    try:
        deleted_count = await repository.delete_history(project_id, user.id, request.history_ids)
    except ProjectNotFoundError:
        raise project_error("project_not_found", "项目不存在", 404) from None
    return {"deleted_count": deleted_count}
