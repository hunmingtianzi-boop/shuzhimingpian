from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ContentCategory = Literal[
    "enterprise_profile",
    "products",
    "case_studies",
    "faqs",
    "unclassified",
]
CandidateStatus = Literal["pending_review", "accepted", "ignored", "conflict"]


class ContentImportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class GenerateContentImportRequest(ContentImportModel):
    batch_id: uuid.UUID
    retry: bool = False


class UpdateContentCandidateRequest(ContentImportModel):
    expected_version: int = Field(ge=1)
    category: ContentCategory
    payload: dict[str, Any]

    @model_validator(mode="after")
    def payload_must_match_category(self) -> "UpdateContentCandidateRequest":
        required = {
            "enterprise_profile": {"company_name", "summary", "industry", "region", "website"},
            "products": {
                "name",
                "category",
                "summary",
                "detail",
                "audience",
                "price_boundary",
            },
            "case_studies": {
                "title",
                "industry",
                "client_display_name",
                "background",
                "solution",
                "result",
            },
            "faqs": {"question", "answer"},
            "unclassified": {"text", "reason"},
        }[self.category]
        if set(self.payload) != required:
            raise ValueError("payload fields must exactly match category contract")
        return self


class ReviewContentCandidateRequest(ContentImportModel):
    expected_version: int = Field(ge=1)
    apply_fields: list[str] = Field(default_factory=list, max_length=8)


class ContentImportCandidateRecord(ContentImportModel):
    id: uuid.UUID
    run_id: uuid.UUID
    category: ContentCategory
    payload: dict[str, Any]
    source_id: str
    source_text: str
    confidence: float = Field(ge=0, le=1)
    status: CandidateStatus
    target_resource_type: str | None = None
    target_resource_id: uuid.UUID | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ContentImportRunRecord(ContentImportModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    status: Literal["processing", "review", "manual_required"]
    provider: str
    model: str
    attempts: int = Field(ge=0, le=2)
    failure_code: str | None = None
    counts: dict[str, int]
    candidates: list[ContentImportCandidateRecord] = Field(default_factory=list)
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ContentImportRunEnvelope(ContentImportModel):
    data: ContentImportRunRecord


class ContentImportRunListEnvelope(ContentImportModel):
    data: list[ContentImportRunRecord]
    total: int = Field(ge=0)


class ContentImportCandidateEnvelope(ContentImportModel):
    data: ContentImportCandidateRecord


__all__ = [name for name in globals() if not name.startswith("_")]
