from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DailyMetric(WorkflowModel):
    day: str
    visits: int = Field(ge=0)
    conversations: int = Field(ge=0)
    leads: int = Field(ge=0)


class DashboardOverview(WorkflowModel):
    generated_at: datetime
    period_days: int = Field(ge=1, le=365)
    visits: int = Field(ge=0)
    unique_visitors: int = Field(ge=0)
    conversations: int = Field(ge=0)
    ai_answers: int = Field(ge=0)
    total_leads: int = Field(ge=0)
    new_leads: int = Field(ge=0)
    pending_gaps: int = Field(ge=0)
    unread_notifications: int = Field(ge=0)
    conversation_rate: float = Field(ge=0, le=1)
    lead_rate: float = Field(ge=0, le=1)
    daily: list[DailyMetric] = Field(default_factory=list)


class DashboardEnvelope(WorkflowModel):
    data: DashboardOverview


class TopicAnalysisItem(WorkflowModel):
    topic: str = Field(min_length=1, max_length=40)
    count: int = Field(ge=1)
    share: float = Field(ge=0, le=1)
    sample_questions: list[str] = Field(default_factory=list, max_length=2)


class TopicAnalysisView(WorkflowModel):
    status: Literal["empty", "not_generated", "ready", "stale"]
    generated_at: datetime | None = None
    period_days: int = Field(ge=1, le=90)
    question_count: int = Field(ge=0)
    analyzed_question_count: int = Field(ge=0)
    summary: str | None = Field(default=None, max_length=600)
    topics: list[TopicAnalysisItem] = Field(default_factory=list, max_length=8)
    provider: str | None = None
    model: str | None = None


class TopicAnalysisEnvelope(WorkflowModel):
    data: TopicAnalysisView


class EmployeeAnalyticsItem(WorkflowModel):
    user_id: uuid.UUID
    membership_id: uuid.UUID
    display_name: str
    role: str
    membership_status: str
    card_count: int = Field(ge=0)
    visits: int = Field(ge=0)
    unique_visitors: int = Field(ge=0)
    conversations: int = Field(ge=0)
    leads: int = Field(ge=0, description="All leads created in the period, regardless of status")
    conversation_rate: float = Field(ge=0, le=1)
    lead_rate: float = Field(ge=0, le=1)
    last_activity_at: datetime | None = None


class EmployeeAnalyticsReconciliation(WorkflowModel):
    card_count: int = Field(ge=0)
    visits: int = Field(ge=0)
    unique_visitors: int = Field(
        ge=0,
        description="Company-wide distinct visitors; reconciles with the dashboard",
    )
    employee_unique_visitors_sum: int = Field(
        ge=0,
        description="Sum of per-employee distinct visitors; may exceed unique_visitors",
    )
    conversations: int = Field(ge=0)
    total_leads: int = Field(ge=0)
    conversation_rate: float = Field(ge=0, le=1)
    lead_rate: float = Field(ge=0, le=1)
    last_activity_at: datetime | None = None


class EmployeeAnalyticsListEnvelope(WorkflowModel):
    data: list[EmployeeAnalyticsItem]
    reconciliation: EmployeeAnalyticsReconciliation
    generated_at: datetime
    period_days: int = Field(ge=1, le=90)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class VisitItem(WorkflowModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    visitor_id: uuid.UUID
    source: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    activity_status: Literal["active", "ended", "estimated", "unknown"] = "unknown"
    last_activity_at: datetime | None = None
    duration_estimated: bool = False
    visitor_channel: Literal["web", "wechat", "wecom"] = "web"
    visitor_identity_type: Literal[
        "anonymous", "wecom_member", "wechat_openid", "wecom_external"
    ] = "anonymous"
    visitor_identity_label: str = "匿名网页访客"
    conversation_count: int = Field(ge=0)


class VisitListEnvelope(WorkflowModel):
    data: list[VisitItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class VisitPageDuration(WorkflowModel):
    page_key: str
    page_title: str
    object_type: str | None = None
    object_id: str | None = None
    duration_seconds: float = Field(ge=0)
    view_count: int = Field(ge=0)
    last_viewed_at: datetime


class VisitQuestion(WorkflowModel):
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    asked_at: datetime
    answer_status: str | None = None


class VisitDetail(VisitItem):
    event_count: int = Field(ge=0)
    page_durations: list[VisitPageDuration] = Field(default_factory=list)
    questions: list[VisitQuestion] = Field(default_factory=list)


class VisitDetailEnvelope(WorkflowModel):
    data: VisitDetail


class VisitorProfileSignalPreview(WorkflowModel):
    label: str
    strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    last_seen_at: datetime


class VisitorProfileListItem(WorkflowModel):
    visitor_id: uuid.UUID
    first_seen_at: datetime
    last_seen_at: datetime
    signal_count: int = Field(ge=0)
    top_interests: list[VisitorProfileSignalPreview]


class PaginationMeta(WorkflowModel):
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class VisitorProfileListEnvelope(WorkflowModel):
    data: list[VisitorProfileListItem]
    meta: PaginationMeta


class VisitorProfileSourceView(WorkflowModel):
    id: uuid.UUID
    visit_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    summary_id: uuid.UUID | None = None
    message_id: uuid.UUID | None = None
    contribution: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    observed_at: datetime


class VisitorProfileSignalView(WorkflowModel):
    id: uuid.UUID
    kind: Literal["interest", "intent"]
    label: str
    strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    first_seen_at: datetime
    last_seen_at: datetime
    evidence_count: int = Field(ge=0)
    retention_expires_at: datetime
    sources: list[VisitorProfileSourceView]


class VisitorProfileDetail(WorkflowModel):
    visitor_id: uuid.UUID
    first_seen_at: datetime
    last_seen_at: datetime
    signals: list[VisitorProfileSignalView]


class VisitorProfileEnvelope(WorkflowModel):
    data: VisitorProfileDetail


class VisitorProfileOverviewLead(WorkflowModel):
    """A consented lead, limited to masked contact data in the 360 view."""

    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    conversation_id: uuid.UUID | None = None
    status: str
    priority: str
    masked_name: str
    masked_contact: str
    company_name: str | None = None
    created_at: datetime


class VisitorProfileOverviewConversation(WorkflowModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    status: str
    primary_intent: str | None = None
    risk_level: str
    started_at: datetime
    last_activity_at: datetime
    message_count: int = Field(ge=0)


class VisitorProfileOverviewGap(WorkflowModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    reason: str
    status: str
    occurrence_count: int = Field(ge=1)
    last_seen_at: datetime


class VisitorProfileOverview(WorkflowModel):
    """Consent-gated profile context; raw IP and unmasked contact are excluded."""

    profile: VisitorProfileDetail
    leads: list[VisitorProfileOverviewLead] = Field(default_factory=list)
    conversations: list[VisitorProfileOverviewConversation] = Field(default_factory=list)
    knowledge_gaps: list[VisitorProfileOverviewGap] = Field(default_factory=list)


class VisitorProfileOverviewEnvelope(WorkflowModel):
    data: VisitorProfileOverview


class ConversationItem(WorkflowModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    visitor_id: uuid.UUID
    visit_id: uuid.UUID | None = None
    status: str
    primary_intent: str | None = None
    risk_level: str
    started_at: datetime
    last_activity_at: datetime
    message_count: int = Field(ge=0)
    has_current_summary: bool


class ConversationListEnvelope(WorkflowModel):
    data: list[ConversationItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class OpportunityCandidateView(WorkflowModel):
    """A high-intent anonymous conversation, not a consented sales lead."""

    conversation_id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    visitor_id: uuid.UUID
    question: str
    reason: str
    score: float = Field(ge=0, le=1)
    has_consented_lead: bool
    last_activity_at: datetime


class OpportunityCandidateListEnvelope(WorkflowModel):
    data: list[OpportunityCandidateView]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class CitationView(WorkflowModel):
    id: uuid.UUID
    chunk_id: uuid.UUID
    rank: int = Field(ge=1)
    score: float
    title: str
    source_type: str
    source_id: str
    snapshot_text: str


class AiRunView(WorkflowModel):
    provider: str
    model: str
    status: str
    first_token_latency_ms: int | None = Field(default=None, ge=0)
    total_latency_ms: int = Field(ge=0)
    retrieval_result: dict[str, Any] = Field(default_factory=dict)
    safety_result: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None


class MessageView(WorkflowModel):
    id: uuid.UUID
    role: str
    content: str
    status: str
    content_redacted: bool
    created_at: datetime
    citations: list[CitationView] = Field(default_factory=list)
    ai_run: AiRunView | None = None


class SummaryView(WorkflowModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    summary: str
    interests: list[str] = Field(default_factory=list)
    strength: str | None = None
    next_step: str | None = None
    risk_notes: str | None = None
    source_message_ids: list[uuid.UUID]
    is_current: bool
    stale_at: datetime | None = None
    approved_at: datetime | None = None
    approved_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationItem):
    messages: list[MessageView]
    current_summary: SummaryView | None = None


class ConversationDetailEnvelope(WorkflowModel):
    data: ConversationDetail


class SummaryEnvelope(WorkflowModel):
    data: SummaryView


class SummaryDraft(WorkflowModel):
    summary: str = Field(min_length=1, max_length=4_000)
    interests: list[str] = Field(default_factory=list, max_length=12)
    strength: Literal["low", "medium", "high", "unknown"] = "unknown"
    primary_intent: Literal[
        "information_research",
        "product_evaluation",
        "cooperation",
        "contact_followup",
        "recruitment",
        "unknown",
    ] = "unknown"
    next_step: str | None = Field(default=None, max_length=2_000)
    risk_notes: str | None = Field(default=None, max_length=2_000)

    @field_validator("interests")
    @classmethod
    def validate_interests(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 160 for item in cleaned):
            raise ValueError("interest tags must not exceed 160 characters")
        return cleaned[:12]


class KnowledgeGapView(WorkflowModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    question: str
    reason: str
    status: str
    suggested_answer: str | None = None
    occurrence_count: int = Field(ge=1)
    last_seen_at: datetime
    approved_version_id: uuid.UUID | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class KnowledgeGapListEnvelope(WorkflowModel):
    data: list[KnowledgeGapView]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class UpdateKnowledgeGapRequest(WorkflowModel):
    suggested_answer: str = Field(min_length=1, max_length=20_000)

    @field_validator("suggested_answer")
    @classmethod
    def reject_blank_answer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("suggested_answer must not be blank")
        return value


class KnowledgeGapEnvelope(WorkflowModel):
    data: KnowledgeGapView


class NotificationView(WorkflowModel):
    id: uuid.UUID
    notification_type: str
    title: str
    body: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None
    read_at: datetime | None = None
    created_at: datetime


class NotificationListEnvelope(WorkflowModel):
    data: list[NotificationView]
    total: int = Field(ge=0)
    unread: int = Field(ge=0)


class NotificationEnvelope(WorkflowModel):
    data: NotificationView


class VisitEventRequest(WorkflowModel):
    event_id: uuid.UUID
    event_type: Literal[
        "page_view",
        "content_view",
        "heartbeat",
        "leave",
        "cta_click",
        "share",
    ]
    object_type: Literal["card", "product", "case", "faq", "contact", "ai"] | None = None
    object_id: str | None = Field(default=None, max_length=160)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def limit_metadata(cls, value: dict[str, str | int | float | bool | None]):
        if len(value) > 12:
            raise ValueError("metadata supports at most 12 fields")
        if any(len(str(key)) > 64 or len(str(item)) > 500 for key, item in value.items()):
            raise ValueError("metadata field is too long")
        return value


class VisitEventView(WorkflowModel):
    id: uuid.UUID
    event_type: str
    occurred_at: datetime


class VisitEventEnvelope(WorkflowModel):
    data: VisitEventView


class LeadCaptureRequest(WorkflowModel):
    conversation_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    mobile: str | None = Field(default=None, min_length=5, max_length=40)
    email: str | None = Field(default=None, min_length=5, max_length=254)
    wechat: str | None = Field(default=None, min_length=2, max_length=100)
    company_name: str | None = Field(default=None, max_length=200)
    demand: str = Field(min_length=1, max_length=4_000)
    interest_tags: list[str] = Field(default_factory=list, max_length=12)
    consent_policy_version: str = Field(min_length=1, max_length=64)
    consent_granted: Literal[True]

    @model_validator(mode="after")
    def require_contact_and_clean_tags(self) -> "LeadCaptureRequest":
        if not any((self.mobile, self.email, self.wechat)):
            raise ValueError("mobile, email or wechat is required")
        self.interest_tags = list(
            dict.fromkeys(item.strip() for item in self.interest_tags if item.strip())
        )
        if any(len(item) > 160 for item in self.interest_tags):
            raise ValueError("interest tag is too long")
        return self


class LeadCreated(WorkflowModel):
    id: uuid.UUID
    status: str
    created_at: datetime


class LeadCreatedEnvelope(WorkflowModel):
    data: LeadCreated


class LeadListItem(WorkflowModel):
    id: uuid.UUID
    card_id: uuid.UUID
    card_display_name: str
    visitor_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    owner_user_id: uuid.UUID
    status: str
    priority: str
    masked_name: str
    masked_contact: str
    company_name: str | None = None
    interest_tags: list[str] = Field(default_factory=list)
    viewed_at: datetime | None = None
    closed_at: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class LeadListEnvelope(WorkflowModel):
    data: list[LeadListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class LeadFollowupView(WorkflowModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID
    followup_type: str
    content: str
    next_at: datetime | None = None
    created_at: datetime


class LeadDetail(LeadListItem):
    name: str
    mobile: str | None = None
    email: str | None = None
    wechat: str | None = None
    demand: str
    followups: list[LeadFollowupView] = Field(default_factory=list)


class LeadDetailEnvelope(WorkflowModel):
    data: LeadDetail


class UpdateLeadRequest(WorkflowModel):
    status: Literal["new", "viewed", "following", "won", "lost", "invalid"]
    priority: Literal["low", "medium", "high"]


class CreateLeadFollowupRequest(WorkflowModel):
    followup_type: Literal["note", "call", "message", "meeting", "status_change"]
    content: str = Field(min_length=1, max_length=10_000)
    next_at: datetime | None = None


class LeadFollowupEnvelope(WorkflowModel):
    data: LeadFollowupView


class PrivacyRequestCreate(WorkflowModel):
    request_type: Literal["access", "correction", "deletion", "withdraw_consent"]
    note: str | None = Field(default=None, max_length=4_000)
    consent_scope: Literal["chat_notice", "lead_contact", "profile_personalization"] | None = None

    @model_validator(mode="after")
    def validate_withdrawal_scope(self) -> "PrivacyRequestCreate":
        if self.request_type == "withdraw_consent" and self.consent_scope is None:
            raise ValueError("consent_scope is required when withdrawing consent")
        if self.request_type != "withdraw_consent" and self.consent_scope is not None:
            raise ValueError("consent_scope only applies to consent withdrawal")
        return self


class PrivacyRequestView(WorkflowModel):
    id: uuid.UUID
    visitor_id: uuid.UUID
    request_type: str
    status: str
    verification_method: str | None = None
    handled_by: uuid.UUID | None = None
    completed_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PrivacyRequestEnvelope(WorkflowModel):
    data: PrivacyRequestView


class PrivacyRequestListEnvelope(WorkflowModel):
    data: list[PrivacyRequestView]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class UpdatePrivacyRequest(WorkflowModel):
    status: Literal["pending", "verified", "in_progress", "completed", "rejected"]
    verification_method: str | None = Field(default=None, max_length=80)


__all__ = [name for name in globals() if not name.startswith("_")]
