from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateExportRequest(ExportModel):
    include_sensitive: bool = False


class ExportAvailabilityView(ExportModel):
    visitors: int = Field(ge=0)
    leads: int = Field(ge=0)
    conversations: int = Field(ge=0)
    generated_at: datetime


class ExportAvailabilityEnvelope(ExportModel):
    data: ExportAvailabilityView


class ExportRequestView(ExportModel):
    id: uuid.UUID
    export_type: Literal["visitors", "leads", "conversations"]
    status: Literal["pending", "processing", "completed", "failed", "expired"]
    include_sensitive: bool
    row_count: int | None = None
    file_name: str | None = None
    content_type: str | None = None
    failure_code: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None


class ExportRequestEnvelope(ExportModel):
    data: ExportRequestView


class ExportRequestListEnvelope(ExportModel):
    data: list[ExportRequestView]
    total: int
    limit: int
    offset: int


__all__ = [
    "CreateExportRequest",
    "ExportAvailabilityEnvelope",
    "ExportAvailabilityView",
    "ExportRequestEnvelope",
    "ExportRequestListEnvelope",
    "ExportRequestView",
]
