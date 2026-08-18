from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.api.catalog_schemas import validate_safe_asset_url
from app.core.text_integrity import ensure_text_tree


class AdminStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EnterpriseReadinessRecord(AdminStrictModel):
    generated_at: datetime
    llm_ready: bool
    unpublished_card_count: int = Field(ge=0)
    processing_import_batch_count: int = Field(ge=0)
    failed_import_batch_count: int = Field(ge=0)


class EnterpriseReadinessEnvelope(AdminStrictModel):
    data: EnterpriseReadinessRecord


class CompanyProfileFact(AdminStrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(min_length=1, max_length=8)
    value: str = Field(min_length=1, max_length=24)


class CompanyProfile(AdminStrictModel):
    id: uuid.UUID
    name: str
    summary: str
    industry: str | None = None
    region: str | None = None
    website: str | None = None
    logo_url: str | None = None
    positioning: str | None = None
    profile_facts: list[CompanyProfileFact] = Field(default_factory=list, max_length=4)
    profile_tags: list[str] = Field(default_factory=list, max_length=3)
    profile_personalization_policy_version: str
    status: str
    onboarding_status: str
    version: int = Field(ge=1)
    updated_at: datetime


class CompanyProfileEnvelope(AdminStrictModel):
    data: CompanyProfile


class UpdateCompanyProfileRequest(AdminStrictModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str = Field(max_length=5_000)
    industry: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=100)
    website: HttpUrl | None = None
    logo_url: str | None = Field(default=None, max_length=2_048)
    positioning: str | None = Field(default=None, max_length=240)
    profile_facts: list[CompanyProfileFact] = Field(default_factory=list, max_length=4)
    profile_tags: list[str] = Field(default_factory=list, max_length=3)
    profile_personalization_policy_version: str = Field(min_length=1, max_length=64)

    _validate_logo_url = field_validator("logo_url")(validate_safe_asset_url)

    @field_validator("profile_tags")
    @classmethod
    def validate_profile_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            key = value.casefold()
            if not value or len(value) > 40:
                raise ValueError("profile tags must contain 1-40 characters")
            if key not in seen:
                normalized.append(value)
                seen.add(key)
        return normalized


class CardProfile(AdminStrictModel):
    id: uuid.UUID
    card_kind: Literal["enterprise", "employee"]
    owner_user_id: uuid.UUID | None = None
    slug: str
    display_name: str
    title: str
    avatar_url: str | None = None
    assistant_name: str | None = None
    welcome_message: str | None = None
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)
    policy_versions: dict[str, str] = Field(default_factory=dict)
    status: str
    onboarding_status: str
    published_at: datetime | None = None
    version: int = Field(ge=1)
    updated_at: datetime


class CardProfileEnvelope(AdminStrictModel):
    data: CardProfile


class EnterpriseSetupResult(AdminStrictModel):
    completed: bool
    company: CompanyProfile
    card: CardProfile


class EnterpriseSetupEnvelope(AdminStrictModel):
    data: EnterpriseSetupResult


class UpdateCardRequest(AdminStrictModel):
    slug: str = Field(
        min_length=3,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$",
    )
    display_name: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2_048)
    assistant_name: str | None = Field(default=None, max_length=120)
    welcome_message: str | None = Field(default=None, max_length=2_000)
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)
    policy_versions: dict[str, str] = Field(default_factory=dict)

    _validate_avatar_url = field_validator("avatar_url")(validate_safe_asset_url)

    @field_validator("suggested_questions")
    @classmethod
    def validate_suggested_questions(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 200 for value in values):
            raise ValueError("suggested questions must contain 1-200 characters")
        return values

    @field_validator("policy_versions")
    @classmethod
    def validate_policy_versions(cls, values: dict[str, str]) -> dict[str, str]:
        allowed = {
            "privacy",
            "chat_notice",
            "lead_consent",
            "profile_personalization",
        }
        if set(values) - allowed:
            raise ValueError("unsupported policy version key")
        if any(not value or len(value) > 64 for value in values.values()):
            raise ValueError("policy versions must contain 1-64 characters")
        return values


class CreateKnowledgeDocumentRequest(AdminStrictModel):
    title: str = Field(min_length=1, max_length=500)
    source_type: str = Field(default="manual", min_length=1, max_length=80)
    source_id: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("title", "source_type", "source_id")
    @classmethod
    def reject_broken_text_encoding(cls, value: str | None) -> str | None:
        return ensure_text_tree(value)


class PutKnowledgeDocumentRequest(AdminStrictModel):
    raw_text: str = Field(min_length=1, max_length=2_000_000)
    title: str | None = Field(default=None, min_length=1, max_length=500)
    visibility: Literal["public", "authenticated", "internal"] = "public"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("raw_text", "title", "metadata")
    @classmethod
    def reject_broken_text_encoding(cls, value: Any) -> Any:
        return ensure_text_tree(value)

    @field_validator("raw_text")
    @classmethod
    def reject_blank_document(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw_text must not be blank")
        return value


class PublishKnowledgeDocumentRequest(AdminStrictModel):
    version_id: uuid.UUID | None = None
    impact_digest: str | None = Field(default=None, min_length=64, max_length=64)


class KnowledgeVersionSummary(AdminStrictModel):
    id: uuid.UUID
    version_number: int = Field(ge=1)
    review_status: str
    chunk_count: int = Field(ge=0)
    indexed_chunk_count: int = Field(ge=0)
    index_status: str | None = None
    index_error_code: str | None = None
    published_at: datetime | None = None
    created_at: datetime


class KnowledgeDocumentRecord(AdminStrictModel):
    id: uuid.UUID
    source_type: str
    source_id: str
    title: str
    status: str
    version: int = Field(ge=1)
    current_version_id: uuid.UUID | None = None
    current_version_number: int | None = Field(default=None, ge=1)
    latest_version: KnowledgeVersionSummary | None = None
    created_at: datetime
    updated_at: datetime


class SelectableFaqRecord(KnowledgeDocumentRecord):
    """Public-safe FAQ projection for the card editor data picker."""

    visibility: Literal["public"] = "public"
    answer: str


class KnowledgeDocumentEnvelope(AdminStrictModel):
    data: KnowledgeDocumentRecord


class KnowledgeDocumentDetail(KnowledgeDocumentRecord):
    raw_text: str | None = None
    visibility: Literal["public", "authenticated", "internal"] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    editable_version_id: uuid.UUID | None = None


class KnowledgeDocumentDetailEnvelope(AdminStrictModel):
    data: KnowledgeDocumentDetail


class KnowledgeDocumentListEnvelope(AdminStrictModel):
    data: list[SelectableFaqRecord | KnowledgeDocumentRecord]
    total: int = Field(ge=0)


class KnowledgeDraftResult(AdminStrictModel):
    document: KnowledgeDocumentRecord
    draft_version: KnowledgeVersionSummary


class KnowledgeDraftEnvelope(AdminStrictModel):
    data: KnowledgeDraftResult


class KnowledgePublishResult(AdminStrictModel):
    document: KnowledgeDocumentRecord
    published_version: KnowledgeVersionSummary
    index_job_id: uuid.UUID
    index_status: str


class KnowledgePublishEnvelope(AdminStrictModel):
    data: KnowledgePublishResult
