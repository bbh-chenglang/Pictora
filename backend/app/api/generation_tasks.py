from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user, get_history_repository
from app.repositories.history_repository import HistoryRepository
from app.schemas.auth import StoredSessionUser
from app.schemas.history import GenerationTaskDetail

router = APIRouter(prefix="/api/generation-tasks", tags=["generation-tasks"])


@router.get("", response_model=list[GenerationTaskDetail])
async def list_generation_tasks(
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> list[GenerationTaskDetail]:
    tasks = await repository.list_generation_tasks(user.id, active_only=True)
    return [GenerationTaskDetail.model_validate(task) for task in tasks]


@router.get("/{task_id}", response_model=GenerationTaskDetail)
async def read_generation_task(
    task_id: int,
    user: StoredSessionUser = Depends(get_current_user),
    repository: HistoryRepository = Depends(get_history_repository),
) -> GenerationTaskDetail:
    task = await repository.get_generation_task(user.id, task_id)
    if task is None:
        raise HTTPException(404, {"error": {"code": "generation_task_not_found", "message": "生成任务不存在"}})
    return GenerationTaskDetail.model_validate(task)
