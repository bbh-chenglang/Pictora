from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import GenerationViewSpec

HistoryKind = Literal["generate", "analyze"]
HistoryStatus = Literal["pending", "completed", "failed"]
HistoryImageRole = Literal["reference", "generated"]
ReferenceCategory = Literal["person", "environment", "object"]


class HistoryImageMeta(BaseModel):
    id: int
    batch_id: int | None = None
    role: HistoryImageRole
    mime_type: str
    filename: str | None = None
    position: int
    batch_position: int | None = None
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


class GenerationBatchSummary(BaseModel):
    id: int
    status: HistoryStatus
    image_count: int
    generated_count: int
    elapsed_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    views: list[GenerationViewSpec] = Field(default_factory=list)
    deleted_positions: list[int] = Field(default_factory=list)
    cancelled_positions: list[int] = Field(default_factory=list)


class HistoryDetail(HistorySummary):
    analysis_text: str | None = None
    completed_at: datetime | None = None
    images: list[HistoryImageMeta]
    batches: list[GenerationBatchSummary]


class GenerationBatchDetail(GenerationBatchSummary):
    history_id: int
    images: list[HistoryImageMeta]


class GenerationTaskDetail(BaseModel):
    id: int
    history_id: int
    project_id: int
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    attempts: int = 0
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    batch_id: int | None = None
    api_key_config_id: int | None = None
    prompt: str
    provider: str
    model: str
    detail: str
    image_count: int
    generated_count: int = 0
    images: list[HistoryImageMeta] = Field(default_factory=list)
    size: str | None = None
    resolution: str | None = None
    views: list[GenerationViewSpec] = Field(default_factory=list)
    deleted_positions: list[int] = Field(default_factory=list)
    cancelled_positions: list[int] = Field(default_factory=list)


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
    output_format: str | None = None
    background: str | None = None
    output_compression: int | None = None
    moderation: str | None = None
    view_label: str | None = None
    references: list[HistoryImageEditReference]
