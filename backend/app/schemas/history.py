from datetime import datetime
from typing import Literal

from pydantic import BaseModel

HistoryKind = Literal["generate", "analyze"]
HistoryStatus = Literal["pending", "completed", "failed"]
HistoryImageRole = Literal["reference", "generated"]
ReferenceCategory = Literal["person", "environment", "object"]


class HistoryImageMeta(BaseModel):
    id: int
    role: HistoryImageRole
    mime_type: str
    filename: str | None = None
    position: int
    url: str
    reference_category: ReferenceCategory | None = None


class HistorySummary(BaseModel):
    id: int
    kind: HistoryKind
    status: HistoryStatus
    prompt: str
    provider: str
    model: str
    detail: str
    image_count: int
    size: str | None = None
    resolution: str | None = None
    elapsed_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class HistoryDetail(HistorySummary):
    analysis_text: str | None = None
    completed_at: datetime | None = None
    images: list[HistoryImageMeta]


class HistoryImageEditReference(BaseModel):
    id: int
    category: ReferenceCategory
    mime_type: str
    filename: str | None = None
    position: int
    url: str


class HistoryImageEditSnapshot(BaseModel):
    history_id: int
    image_id: int
    api_key_config_id: int | None = None
    prompt: str
    provider: str
    model: str
    detail: str
    image_count: int
    size: str | None = None
    resolution: str | None = None
    references: list[HistoryImageEditReference]
