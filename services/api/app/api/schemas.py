from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateVisitRequest(StrictModel):
    source: str = Field(min_length=1, max_length=64)
    campaign: str | None = Field(default=None, max_length=128)
    privacy_notice_version: str = Field(min_length=1, max_length=64)
    profile_link_token: str | None = Field(default=None, min_length=1, max_length=2_048)


class VisitSession(StrictModel):
    visit_id: uuid.UUID
    visitor_session_token: str
    expires_at: datetime
    profile_link_token: str | None = None


class VisitEnvelope(StrictModel):
    data: VisitSession


class PublicCompany(StrictModel):
    id: uuid.UUID
    name: str
    summary: str
    industry: str | None = None
    region: str | None = None
    website: str | None = None
    logo_url: str | None = None
    official_card_slug: str | None = None


class AiAssistantPublicConfig(StrictModel):
    available: bool
    display_name: str
    disclosure: str
    welcome_message: str
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)


class PublicFaqItem(StrictModel):
    id: str
    document_id: uuid.UUID
    question: str
    answer: str
    source_label: str


class PolicyVersions(StrictModel):
    privacy: str
    chat_notice: str
    lead_consent: str
    profile_personalization: str


class PublicWeComContact(StrictModel):
    available: bool
    qr_code_url: str | None = None
    label: str = "添加企业微信"


class PublicCard(StrictModel):
    id: uuid.UUID
    slug: str
    card_kind: Literal["enterprise", "employee"]
    display_name: str
    title: str
    avatar_url: str | None = None
    business_summary: str | None = None
    contact_fields: list[dict[str, str]] = Field(default_factory=list)
    wecom_contact: PublicWeComContact | None = None
    company: PublicCompany
    featured_products: list[dict[str, Any]] = Field(default_factory=list)
    featured_cases: list[dict[str, Any]] = Field(default_factory=list)
    faq_items: list[PublicFaqItem] = Field(default_factory=list)
    ai_assistant: AiAssistantPublicConfig
    policy_versions: PolicyVersions
    enterprise_template: dict[str, Any] | None = None


class PublicCardEnvelope(StrictModel):
    data: PublicCard


class ConsentRequest(StrictModel):
    scope: Literal["chat_notice", "lead_contact", "profile_personalization"]
    policy_version: str = Field(min_length=1, max_length=64)
    granted: bool


class ConsentRecord(StrictModel):
    id: uuid.UUID
    scope: Literal["chat_notice", "lead_contact", "profile_personalization"]
    policy_version: str
    granted: bool
    recorded_at: datetime
    profile_link_token: str | None = None


class ConsentEnvelope(StrictModel):
    data: ConsentRecord


class CreateConversationRequest(StrictModel):
    chat_notice_version: str = Field(min_length=1, max_length=64)


class ConversationRecord(StrictModel):
    id: uuid.UUID
    status: Literal["active", "closed", "expired", "blocked"]
    created_at: datetime


class ConversationEnvelope(StrictModel):
    data: ConversationRecord


class CreateMessageRequest(StrictModel):
    content: str = Field(min_length=1, max_length=2_000)


class MessageStarted(StrictModel):
    message_id: uuid.UUID
    request_id: str


class MessageDelta(StrictModel):
    text: str


class MessageCitation(StrictModel):
    citation_id: uuid.UUID
    label: str
    source_type: str


class MessageCompleted(StrictModel):
    message_id: uuid.UUID
    finish_reason: Literal["stop", "refusal", "length", "content_filter"]
    lead_prompt: bool = False


class MessageError(StrictModel):
    code: str
    retryable: bool
    request_id: str
