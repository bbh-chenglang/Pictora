from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.history import HistorySummary


def validate_project_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("项目名称不能为空")
    if len(name) > 80:
        raise ValueError("项目名称不能超过 80 个字符")
    return name


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    _normalize_name = field_validator("name")(validate_project_name)


class ProjectRenameRequest(ProjectCreateRequest):
    pass


class HistoryDeleteRequest(BaseModel):
    history_ids: list[int] = Field(min_length=1, max_length=100)


class Project(BaseModel):
    id: int
    user_id: int
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectSummary(Project):
    history: list[HistorySummary]
    history_count: int


class ProjectDeleteResult(BaseModel):
    deleted_history_count: int
    selected_project_id: int
    projects: list[ProjectSummary]
