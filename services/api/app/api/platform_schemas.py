from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.api.content_import_schemas import ContentImportRunRecord
from app.api.knowledge_import_schemas import KnowledgeImportBatchRecord

PLATFORM_FORBIDDEN_RESPONSE_FIELDS = frozenset(
    {
        "admin_password",
        "api_key",
        "api_key_ciphertext",
        "conversation_body",
        "email",
        "knowledge_body",
        "lead_body",
        "mobile",
        "password",
        "payload_ciphertext",
        "raw_text",
        "secret_ref",
        "visitor_email",
        "visitor_id",
        "visitor_mobile",
        "wechat",
    }
)


class PlatformModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateEnterpriseRequest(PlatformModel):
    tenant_slug: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$",
    )
    tenant_name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    admin_account: str = Field(min_length=3, max_length=200)
    admin_display_name: str = Field(min_length=1, max_length=120)
    admin_password: SecretStr
    initial_card_title: str | None = Field(default=None, max_length=200)

    @field_validator("admin_account")
    @classmethod
    def validate_account(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("admin_account must not contain whitespace")
        return value.casefold()

    @field_validator("admin_password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        if not 12 <= len(value.get_secret_value()) <= 200:
            raise ValueError("admin_password must contain 12-200 characters")
        return value


class EnterpriseRecord(PlatformModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    company_id: uuid.UUID
    company_name: str
    company_status: str
    admin_user_id: uuid.UUID
    admin_membership_id: uuid.UUID
    initial_card_id: uuid.UUID
    initial_card_slug: str
    created_at: datetime


class EnterpriseEnvelope(PlatformModel):
    data: EnterpriseRecord


class EnterpriseListItem(PlatformModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    company_id: uuid.UUID
    company_name: str
    status: str
    created_at: datetime


class EnterpriseListEnvelope(PlatformModel):
    data: list[EnterpriseListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PlatformCardProjection(PlatformModel):
    id: uuid.UUID
    card_kind: Literal["enterprise", "employee"]
    display_name: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=200)
    status: str = Field(min_length=1, max_length=40)
    updated_at: datetime
    share_url: AnyHttpUrl | None = None

    @model_validator(mode="after")
    def share_url_requires_a_published_card(self) -> Self:
        if self.share_url is not None and self.status != "published":
            raise ValueError("share_url is only allowed for published cards")
        return self


class PlatformEnterpriseDetail(PlatformModel):
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    company_id: uuid.UUID
    company_name: str
    status: str
    version: int = Field(ge=1)
    onboarding_status: str
    profile_completion: int = Field(ge=0, le=100)
    employee_count: int = Field(ge=0)
    card_count: int = Field(ge=0)
    published_card_count: int = Field(ge=0)
    visits_30d: int = Field(ge=0)
    conversations_30d: int = Field(ge=0)
    leads_30d: int = Field(ge=0)
    cards: list[PlatformCardProjection] = Field(default_factory=list)
    business_profile: list[dict[str, object]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def counts_are_consistent(self) -> Self:
        if self.published_card_count > self.card_count:
            raise ValueError("published_card_count cannot exceed card_count")
        return self


class PlatformEnterpriseDetailEnvelope(PlatformModel):
    data: PlatformEnterpriseDetail


class TransitionPlatformEnterpriseRequest(PlatformModel):
    expected_version: int = Field(ge=1)
    target_status: Literal["active", "suspended"]
    reason: str = Field(min_length=3, max_length=500)


class PlatformEnterpriseLifecycleRecord(PlatformModel):
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    previous_status: Literal["active", "suspended", "disabled"]
    status: Literal["active", "suspended"]
    version: int = Field(ge=1)
    changed: bool
    updated_at: datetime


class PlatformEnterpriseLifecycleEnvelope(PlatformModel):
    data: PlatformEnterpriseLifecycleRecord


class PlatformOverviewRecord(PlatformModel):
    generated_at: datetime
    enterprise_count: int = Field(ge=0)
    active_enterprise_count: int = Field(ge=0)
    onboarding_count: int = Field(ge=0)
    published_card_count: int = Field(ge=0)
    visits_30d: int = Field(ge=0)
    conversations_30d: int = Field(ge=0)
    leads_30d: int = Field(ge=0)
    failed_task_count: int = Field(ge=0)
    llm_ready: bool
    import_ready: bool


class PlatformOverviewEnvelope(PlatformModel):
    data: PlatformOverviewRecord


class PlatformCompanyAggregate(PlatformModel):
    company_id: uuid.UUID
    company_name: str
    employee_count: int = Field(ge=0)
    visits_30d: int = Field(ge=0)
    unique_visitors_30d: int = Field(ge=0)
    last_visit_at: datetime | None = None


class PlatformCompanyAggregateListEnvelope(PlatformModel):
    data: list[PlatformCompanyAggregate]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PlatformTaskRecord(PlatformModel):
    id: uuid.UUID
    task_type: str
    business_label: str
    status: str
    company_id: uuid.UUID
    company_name: str
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime


class PlatformTaskListEnvelope(PlatformModel):
    data: list[PlatformTaskRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PlatformAuditRecord(PlatformModel):
    id: uuid.UUID
    actor_display_name: str
    action: str
    business_label: str
    resource_type: str
    resource_id: uuid.UUID | None = None
    result: str
    created_at: datetime


class PlatformAuditListEnvelope(PlatformModel):
    data: list[PlatformAuditRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PlatformServiceHealthRecord(PlatformModel):
    service: Literal["api", "database", "redis", "object_storage", "worker"]
    status: Literal["healthy", "degraded", "unavailable"]
    checked_at: datetime
    latency_ms: int | None = Field(default=None, ge=0)
    error_code: str | None = None


class PlatformServiceHealthEnvelope(PlatformModel):
    data: list[PlatformServiceHealthRecord]


class PlatformLlmProfileFields(PlatformModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: Literal["chat_main"] = "chat_main"
    provider: str = Field(min_length=1, max_length=80)
    base_url: AnyHttpUrl
    model: str = Field(min_length=1, max_length=160)
    thinking: Literal["enabled", "disabled"] = "disabled"
    reasoning_effort: Literal["high", "max"] | None = None
    timeout_seconds: float = Field(default=30, ge=2, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    max_concurrency: int = Field(default=20, ge=1, le=500)
    max_output_tokens: int = Field(default=1000, ge=128, le=8192)
    temperature: float = Field(default=0.1, ge=0, le=2)
    daily_budget_cny: float = Field(default=100, ge=0)
    input_price_cny_per_million: float = Field(default=0, ge=0)
    output_price_cny_per_million: float = Field(default=0, ge=0)
    allow_general_answers: bool = False
    faq_fast_path_enabled: bool = False
    enabled: bool = True

    @field_validator("base_url")
    @classmethod
    def base_url_has_no_credential_or_request_parts(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("base_url must not contain credentials, query or fragment")
        return value

    @model_validator(mode="after")
    def thinking_fields_are_consistent(self) -> Self:
        if self.thinking == "enabled" and self.temperature != 0.1:
            raise ValueError("temperature must remain neutral while thinking is enabled")
        return self


class CreatePlatformLlmProfileRequest(PlatformLlmProfileFields):
    api_key: SecretStr = Field(min_length=1, max_length=4096)


class UpdatePlatformLlmProfileRequest(PlatformModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: str | None = Field(default=None, min_length=1, max_length=80)
    base_url: AnyHttpUrl | None = None
    model: str | None = Field(default=None, min_length=1, max_length=160)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)
    thinking: Literal["enabled", "disabled"] | None = None
    reasoning_effort: Literal["high", "max"] | None = None
    timeout_seconds: float | None = Field(default=None, ge=2, le=120)
    max_retries: int | None = Field(default=None, ge=0, le=5)
    max_concurrency: int | None = Field(default=None, ge=1, le=500)
    max_output_tokens: int | None = Field(default=None, ge=128, le=8192)
    temperature: float | None = Field(default=None, ge=0, le=2)
    daily_budget_cny: float | None = Field(default=None, ge=0)
    input_price_cny_per_million: float | None = Field(default=None, ge=0)
    output_price_cny_per_million: float | None = Field(default=None, ge=0)
    allow_general_answers: bool | None = None
    faq_fast_path_enabled: bool | None = None
    enabled: bool | None = None

    @field_validator("base_url")
    @classmethod
    def update_base_url_has_no_credential_or_request_parts(
        cls, value: AnyHttpUrl | None
    ) -> AnyHttpUrl | None:
        unsafe_parts = value and (value.username or value.password or value.query or value.fragment)
        if unsafe_parts:
            raise ValueError("base_url must not contain credentials, query or fragment")
        return value


class ActivatePlatformLlmProfileRequest(PlatformModel):
    expected_version: int = Field(ge=1)
    expected_active_profile_id: uuid.UUID | None = None


class TestPlatformLlmProfileRequest(PlatformModel):
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=4096)


class PlatformLlmProfileRecord(PlatformModel):
    id: uuid.UUID
    name: str
    purpose: Literal["chat_main"]
    provider: str
    base_url: AnyHttpUrl
    model: str
    thinking: Literal["enabled", "disabled"] = "disabled"
    reasoning_effort: Literal["high", "max"] | None = None
    timeout_seconds: float = 30
    max_retries: int = 2
    max_concurrency: int = 20
    max_output_tokens: int = 1000
    temperature: float = 0.1
    daily_budget_cny: float = 100
    input_price_cny_per_million: float = 0
    output_price_cny_per_million: float = 0
    allow_general_answers: bool = False
    faq_fast_path_enabled: bool = False
    key_configured: bool
    key_hint: str | None = Field(default=None, max_length=32)
    enabled: bool
    is_active: bool
    version: int = Field(ge=1)
    last_test_status: Literal["untested", "succeeded", "failed"] = "untested"
    last_test_latency_ms: int | None = Field(default=None, ge=0)
    last_tested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PlatformLlmProfileEnvelope(PlatformModel):
    data: PlatformLlmProfileRecord


class PlatformLlmProfileListEnvelope(PlatformModel):
    data: list[PlatformLlmProfileRecord]


class PlatformLlmConnectionTestRecord(PlatformModel):
    status: Literal["succeeded", "failed"]
    provider: str
    model: str
    latency_ms: int = Field(ge=0)
    error_code: str | None = None


class PlatformLlmConnectionTestEnvelope(PlatformModel):
    data: PlatformLlmConnectionTestRecord


class StartPlatformOnboardingRequest(PlatformModel):
    tenant_slug: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$",
    )
    tenant_name: str | None = Field(default=None, min_length=1, max_length=200)
    admin_account: str = Field(min_length=3, max_length=200)
    admin_display_name: str = Field(min_length=1, max_length=120)

    @field_validator("admin_account")
    @classmethod
    def validate_onboarding_account(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("admin_account must not contain whitespace")
        return value.casefold()

class PlatformOnboardingSuggestionSource(PlatformModel):
    import_item_id: uuid.UUID
    file_name: str = Field(min_length=1, max_length=255)
    document_id: uuid.UUID | None = None
    excerpt: str | None = Field(default=None, max_length=500)


class PlatformOnboardingSuggestion(PlatformModel):
    field: str = Field(min_length=1, max_length=80)
    value: str = Field(max_length=20_000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    generation_version: int = Field(ge=1)
    sources: list[PlatformOnboardingSuggestionSource] = Field(default_factory=list)


class TemporaryCredentialDelivery(PlatformModel):
    account: str = Field(min_length=3, max_length=200)
    temporary_password: str = Field(min_length=12, max_length=200)
    expires_at: datetime
    shown_once: Literal[True] = True


class PlatformOnboardingSessionRecord(PlatformModel):
    id: uuid.UUID
    status: Literal[
        "draft",
        "processing",
        "review",
        "manual_required",
        "ready_to_confirm",
        "confirmed",
        "cancelled",
        "expired",
        "failed",
    ]
    tenant_slug: str
    tenant_name: str | None = None
    admin_account: str | None = Field(default=None, max_length=200)
    admin_display_name: str | None = Field(default=None, max_length=120)
    initial_card_display_name: str | None = Field(default=None, max_length=160)
    initial_card_title: str | None = Field(default=None, max_length=200)
    version: int = Field(ge=1)
    import_batch_ids: list[uuid.UUID] = Field(default_factory=list)
    suggestions: list[PlatformOnboardingSuggestion] = Field(default_factory=list)
    business_profile: list[PlatformOnboardingSuggestion] = Field(default_factory=list)
    content_review: ContentImportRunRecord | None = None
    expires_at: datetime | None = None
    confirmed_enterprise: EnterpriseRecord | None = None
    credential_delivery: TemporaryCredentialDelivery | None = None
    created_at: datetime
    updated_at: datetime


class PlatformOnboardingSessionEnvelope(PlatformModel):
    data: PlatformOnboardingSessionRecord


class PlatformOnboardingSessionListEnvelope(PlatformModel):
    data: list[PlatformOnboardingSessionRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PlatformOnboardingImportStatusRecord(PlatformModel):
    session_id: uuid.UUID
    settled: bool
    batches: list[KnowledgeImportBatchRecord] = Field(default_factory=list)


class PlatformOnboardingImportStatusEnvelope(PlatformModel):
    data: PlatformOnboardingImportStatusRecord


class ConfirmPlatformOnboardingRequest(PlatformModel):
    expected_version: int = Field(ge=1)
    tenant_name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=5000)
    website: AnyHttpUrl | None = None
    initial_card_display_name: str = Field(min_length=1, max_length=120)
    initial_card_title: str | None = Field(default=None, max_length=200)
    assistant_name: str | None = Field(default=None, max_length=120)
    welcome_message: str | None = Field(default=None, max_length=1000)


class GeneratePlatformOnboardingSuggestionsRequest(PlatformModel):
    expected_version: int = Field(ge=1)


class CancelPlatformOnboardingRequest(PlatformModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


__all__ = [
    "ActivatePlatformLlmProfileRequest",
    "CancelPlatformOnboardingRequest",
    "ConfirmPlatformOnboardingRequest",
    "CreateEnterpriseRequest",
    "CreatePlatformLlmProfileRequest",
    "EnterpriseEnvelope",
    "EnterpriseListEnvelope",
    "EnterpriseListItem",
    "EnterpriseRecord",
    "GeneratePlatformOnboardingSuggestionsRequest",
    "PLATFORM_FORBIDDEN_RESPONSE_FIELDS",
    "PlatformCardProjection",
    "PlatformAuditListEnvelope",
    "PlatformAuditRecord",
    "PlatformCompanyAggregate",
    "PlatformCompanyAggregateListEnvelope",
    "PlatformEnterpriseDetail",
    "PlatformEnterpriseDetailEnvelope",
    "PlatformEnterpriseLifecycleEnvelope",
    "PlatformEnterpriseLifecycleRecord",
    "PlatformLlmConnectionTestEnvelope",
    "PlatformLlmConnectionTestRecord",
    "PlatformLlmProfileEnvelope",
    "PlatformLlmProfileFields",
    "PlatformLlmProfileListEnvelope",
    "PlatformLlmProfileRecord",
    "PlatformOnboardingSessionEnvelope",
    "PlatformOnboardingImportStatusEnvelope",
    "PlatformOnboardingImportStatusRecord",
    "PlatformOnboardingSessionListEnvelope",
    "PlatformOnboardingSessionRecord",
    "PlatformOnboardingSuggestion",
    "PlatformOnboardingSuggestionSource",
    "PlatformOverviewEnvelope",
    "PlatformOverviewRecord",
    "PlatformServiceHealthEnvelope",
    "PlatformServiceHealthRecord",
    "PlatformTaskListEnvelope",
    "PlatformTaskRecord",
    "StartPlatformOnboardingRequest",
    "TestPlatformLlmProfileRequest",
    "TransitionPlatformEnterpriseRequest",
    "UpdatePlatformLlmProfileRequest",
]
