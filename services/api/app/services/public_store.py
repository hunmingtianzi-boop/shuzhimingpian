from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy import case, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry
from app.ai.schemas import AIAnswer, ChatMessage, ForbiddenTopicPolicy, RefusalCode
from app.api.catalog_schemas import EnterpriseTemplateDocument
from app.api.errors import ApiError
from app.api.schemas import (
    AiAssistantPublicConfig,
    ConsentRequest,
    ConversationRecord,
    CreateConversationRequest,
    CreateVisitRequest,
    PolicyVersions,
    PublicCard,
    PublicCompany,
    PublicFaqItem,
    PublicWeComContact,
    VisitSession,
)
from app.api.schemas import (
    ConsentRecord as ConsentRecordSchema,
)
from app.api.schemas import (
    MessageCitation as MessageCitationSchema,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.core.redaction import redact_sensitive_text
from app.core.tokens import (
    ProfileLinkTokenError,
    VisitorPrincipal,
    decode_profile_link_token,
    issue_profile_link_token,
    issue_visitor_token,
)
from app.db.models import (
    AIRun,
    Card,
    CardKind,
    CaseStudy,
    Company,
    ConsentRecord,
    ConsentScope,
    ContentStatus,
    Conversation,
    ConversationStatus,
    ForbiddenTopic,
    IdempotencyKey,
    IdempotencyStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeGap,
    KnowledgeGapStatus,
    LifecycleStatus,
    Membership,
    Message,
    MessageCitation,
    MessageRole,
    MessageStatus,
    ModelConfig,
    Product,
    PromptStatus,
    PromptVersion,
    User,
    Visibility,
    Visit,
    Visitor,
    VisitorProfileSignal,
    VisitSummary,
    WeComCardContactWay,
)


@dataclass(frozen=True, slots=True)
class CardScope:
    card_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    slug: str


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    record: IdempotencyKey
    created: bool
    replay: bool


@dataclass(frozen=True, slots=True)
class PreparedMessage:
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    question: str
    idempotency_key: str
    card_slug: str
    replay: bool = False


@dataclass(frozen=True, slots=True)
class PublicEmployeeIdentity:
    display_name: str
    job_title: str | None
    avatar_url: str | None
    business_summary: str | None
    email: str | None
    mobile: str | None


@dataclass(frozen=True, slots=True)
class StoredCitation:
    id: uuid.UUID
    label: str
    source_type: str


@dataclass(frozen=True, slots=True)
class StoredAnswer:
    message_id: uuid.UUID
    text: str
    finish_reason: Literal["stop", "refusal", "length", "content_filter"]
    citations: tuple[StoredCitation, ...]
    lead_prompt: bool = False


def canonical_request_hash(action: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"action": action, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PublicStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._cipher = PiiCipher.from_settings(settings)

    async def get_public_card(self, *, slug: str) -> PublicCard:
        async with self._sessions() as session, session.begin():
            scope = await self._resolve_public_card(session, slug)
            card = await session.get(Card, scope.card_id)
            company = await session.get(Company, scope.company_id)
            if card is None or company is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
            employee_identity = (
                await _public_employee_identity(session, card=card, cipher=self._cipher)
                if card.card_kind == CardKind.EMPLOYEE
                else None
            )
            official_card_slug = await _published_enterprise_card_slug(
                session,
                card=card,
            )
            card_settings = card.settings if isinstance(card.settings, dict) else {}
            company_settings = company.settings if isinstance(company.settings, dict) else {}
            public_template = (
                await _public_enterprise_template(
                    session,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    value=card_settings.get("enterprise_template_published"),
                )
                if card_settings.get("enterprise_template_published")
                else None
            )
            knowledge_count = (
                await session.execute(
                    select(func.count(KnowledgeDocument.id)).where(
                        KnowledgeDocument.tenant_id == scope.tenant_id,
                        KnowledgeDocument.company_id == company.id,
                        KnowledgeDocument.status == ContentStatus.PUBLISHED,
                        KnowledgeDocument.current_version_id.is_not(None),
                    )
                )
            ).scalar_one()
            faq_items = await _public_faq_items(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                enterprise_template=public_template,
            )
            policies = card_settings.get("policy_versions", {})
            if not isinstance(policies, dict):
                policies = {}
            suggested = card_settings.get("suggested_questions", [])
            if not isinstance(suggested, list):
                suggested = []
            suggested_questions = [str(item) for item in suggested if isinstance(item, str)][:6]
            # WeCom contact ways are optional public-card enrichment. During a
            # rolling deployment an older database can briefly serve the newer
            # API before migration 0026 creates this table; the card itself must
            # remain available in that window.
            has_wecom_contact_table = True
            if session.get_bind().dialect.name == "postgresql":
                has_wecom_contact_table = bool(
                    await session.scalar(
                        text("SELECT to_regclass('public.wecom_card_contact_ways') IS NOT NULL")
                    )
                )
            wecom_contact = (
                await session.scalar(
                    select(WeComCardContactWay).where(
                        WeComCardContactWay.tenant_id == scope.tenant_id,
                        WeComCardContactWay.company_id == scope.company_id,
                        WeComCardContactWay.card_id == card.id,
                        WeComCardContactWay.revoked_at.is_(None),
                    )
                )
                if has_wecom_contact_table
                else None
            )
            return PublicCard(
                id=card.id,
                slug=card.slug,
                card_kind=card.card_kind,
                display_name=(
                    employee_identity.display_name
                    if employee_identity is not None
                    else card.display_name
                ),
                title=(
                    employee_identity.job_title or company.name
                    if employee_identity is not None
                    else str(card_settings.get("title") or company.name)
                ),
                avatar_url=(
                    employee_identity.avatar_url
                    if employee_identity is not None
                    else _optional_string(card_settings.get("avatar_url"))
                ),
                business_summary=(
                    employee_identity.business_summary if employee_identity is not None else None
                ),
                company=PublicCompany(
                    id=company.id,
                    name=company.name,
                    summary=str(company_settings.get("summary") or ""),
                    industry=company.industry,
                    region=_optional_string(company_settings.get("region")),
                    website=_optional_string(company_settings.get("website")),
                    logo_url=_optional_string(company_settings.get("logo_url")),
                    official_card_slug=official_card_slug,
                ),
                contact_fields=(
                    _employee_contact_fields(
                        employee_identity,
                        _employee_contact_visibility(card_settings),
                    )
                    if employee_identity is not None
                    else _public_dict_list(
                        card_settings.get("contact_fields"),
                        allowed_keys=("label", "value", "href"),
                    )
                ),
                wecom_contact=(
                    PublicWeComContact(
                        available=wecom_contact.qr_code_url_ciphertext is not None,
                        qr_code_url=(
                            self._cipher.decrypt(wecom_contact.qr_code_url_ciphertext)
                            if wecom_contact.qr_code_url_ciphertext
                            else None
                        ),
                    )
                    if wecom_contact is not None
                    else None
                ),
                featured_products=_public_dict_list(
                    company_settings.get("featured_products"),
                    allowed_keys=("title", "description", "url"),
                ),
                featured_cases=_public_dict_list(
                    company_settings.get("featured_cases"),
                    allowed_keys=("title", "description", "industry", "url"),
                ),
                faq_items=faq_items,
                ai_assistant=AiAssistantPublicConfig(
                    # This value represents card/content readiness only. The
                    # public route combines it with the same dynamic LLM
                    # resolver used by Chat so database profiles take effect
                    # without a process restart.
                    available=knowledge_count > 0,
                    display_name=str(
                        card_settings.get("assistant_name") or f"{company.name} AI 助手"
                    ),
                    disclosure="回答由 AI 基于企业已发布资料生成，请以人工确认为准。",
                    welcome_message=str(
                        card_settings.get("welcome_message")
                        or "你好，我可以根据已发布的企业资料回答问题。"
                    ),
                    suggested_questions=suggested_questions,
                ),
                policy_versions=PolicyVersions(
                    privacy=str(policies.get("privacy") or "privacy-v1"),
                    chat_notice=str(policies.get("chat_notice") or "chat-notice-v1"),
                    lead_consent=str(policies.get("lead_consent") or "lead-consent-v1"),
                    profile_personalization=str(_company_profile_policy(company)),
                ),
                enterprise_template=public_template,
            )

    async def create_visit(
        self,
        *,
        slug: str,
        request: CreateVisitRequest,
        idempotency_key: str,
        visitor_channel: str = "web",
    ) -> VisitSession:
        async with self._sessions() as session, session.begin():
            scope = await self._resolve_public_card(session, slug)
            card = await session.get(Card, scope.card_id)
            company = await session.get(Company, scope.company_id)
            if card is None or company is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
            if request.privacy_notice_version != _policy_version(card, ConsentScope.BROWSE_NOTICE):
                raise _policy_version_mismatch()
            linked_consent = await self._valid_profile_link_consent(
                session,
                token=request.profile_link_token,
                scope=scope,
                expected_policy=_company_profile_policy(company),
            )
            claim = await self._claim_idempotency(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                scope=f"public.visit:{scope.card_id}",
                key=idempotency_key,
                request_hash=canonical_request_hash("create_visit", request.model_dump()),
            )
            if claim.replay:
                if claim.record.resource_id is None:
                    raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "请求仍在处理中")
                visit = await session.get(Visit, claim.record.resource_id)
                if visit is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等记录已失效，请重新请求")
                visitor_id = visit.visitor_id
                visit_id = visit.id
                latest_profile_consent = await self._latest_profile_consent(
                    session,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    visitor_id=visitor_id,
                )
                if latest_profile_consent is not None and not latest_profile_consent.granted:
                    raise ApiError(
                        409,
                        "PROFILE_LINK_REPLAY_INVALID",
                        "画像关联授权已变化，请重新开始访问",
                    )
                if request.profile_link_token and (
                    linked_consent is None or linked_consent.visitor_id != visitor_id
                ):
                    raise ApiError(
                        409,
                        "PROFILE_LINK_REPLAY_INVALID",
                        "画像关联授权已变化，请重新开始访问",
                    )
            else:
                visitor_id = linked_consent.visitor_id if linked_consent else uuid.uuid4()
                visit_id = uuid.uuid4()
                visitor = None
                if linked_consent is None:
                    visitor = Visitor(
                        id=visitor_id,
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                        anonymous_hash=self._anonymous_visitor_hash(scope.company_id, visitor_id),
                    )
                visit = Visit(
                    id=visit_id,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    card_id=scope.card_id,
                    visitor_id=visitor_id,
                    source=request.source,
                    context={
                        "campaign": request.campaign,
                        "privacy_notice_version": request.privacy_notice_version,
                        "visitor_channel": (
                            visitor_channel
                            if visitor_channel in {"web", "wechat", "wecom"}
                            else "web"
                        ),
                        "visitor_identity_type": "anonymous",
                    },
                )
                # These models intentionally do not expose ORM relationships.
                # Flush the parent explicitly so SQLAlchemy cannot schedule the
                # visit insert ahead of its composite visitor foreign key.
                if visitor is not None:
                    session.add(visitor)
                    await session.flush()
                else:
                    await session.execute(
                        update(Visitor)
                        .where(
                            Visitor.id == visitor_id,
                            Visitor.tenant_id == scope.tenant_id,
                            Visitor.company_id == scope.company_id,
                        )
                        .values(last_seen_at=datetime.now(UTC))
                    )
                session.add(visit)
                await session.flush()
                self._complete_idempotency(
                    claim.record,
                    resource_type="visit",
                    resource_id=visit_id,
                    status_code=201,
                    response_body={"visit_id": str(visit_id)},
                )

        token, expires_epoch = issue_visitor_token(
            signing_key=self._settings.jwt_signing_key.get_secret_value(),
            issuer=self._settings.app_name,
            ttl_seconds=self._settings.visitor_token_ttl_seconds,
            visitor_id=visitor_id,
            visit_id=visit_id,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            card_id=scope.card_id,
        )
        return VisitSession(
            visit_id=visit_id,
            visitor_session_token=token,
            expires_at=datetime.fromtimestamp(expires_epoch, tz=UTC),
            profile_link_token=(
                request.profile_link_token
                if linked_consent is not None and linked_consent.visitor_id == visitor_id
                else None
            ),
        )

    async def record_consent(
        self,
        *,
        slug: str,
        principal: VisitorPrincipal,
        request: ConsentRequest,
        idempotency_key: str,
    ) -> ConsentRecordSchema:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal, card_slug=slug)
            card = await self._require_principal_card(session, principal, slug)
            requested_scope = ConsentScope(request.scope)
            company = await session.get(Company, principal.company_id)
            expected_policy = (
                _company_profile_policy(company)
                if requested_scope == ConsentScope.PROFILE_PERSONALIZATION and company is not None
                else _policy_version(card, requested_scope)
            )
            if request.policy_version != expected_policy:
                raise _policy_version_mismatch()
            if requested_scope == ConsentScope.PROFILE_PERSONALIZATION:
                await self._lock_profile_visitor(session, principal.visitor_id)
            if request.scope == ConsentScope.PROFILE_PERSONALIZATION.value and request.granted:
                latest_profile_consent = await self._latest_profile_consent(
                    session,
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    visitor_id=principal.visitor_id,
                )
                if (
                    latest_profile_consent is not None
                    and not latest_profile_consent.granted
                    and principal.issued_at_ms
                    <= int(latest_profile_consent.recorded_at.timestamp() * 1_000)
                ):
                    raise ApiError(
                        401,
                        "VISITOR_SESSION_STALE",
                        "访客会话早于最近撤回记录，请重新开始访问",
                    )
            claim = await self._claim_idempotency(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                scope=f"public.consent:{principal.visitor_id}",
                key=idempotency_key,
                request_hash=canonical_request_hash("record_consent", request.model_dump()),
            )
            if claim.replay:
                if claim.record.resource_id is None:
                    raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "请求仍在处理中")
                record = await session.get(ConsentRecord, claim.record.resource_id)
                if record is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等记录已失效，请重新请求")
            else:
                granted = bool(request.granted)
                record = ConsentRecord(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    visitor_id=principal.visitor_id,
                    scope=ConsentScope(request.scope),
                    policy_version=request.policy_version,
                    granted=granted,
                    expires_at=(
                        datetime.now(UTC)
                        + timedelta(seconds=self._settings.profile_link_token_ttl_seconds)
                        if request.scope == ConsentScope.PROFILE_PERSONALIZATION.value and granted
                        else None
                    ),
                    evidence={
                        "card_id": str(principal.card_id),
                        "visit_id": str(principal.visit_id),
                        "token_id_hash": hashlib.sha256(
                            str(principal.token_id).encode("ascii")
                        ).hexdigest(),
                    },
                )
                session.add(record)
                await session.flush()
                if record.scope == ConsentScope.PROFILE_PERSONALIZATION and not record.granted:
                    await session.execute(
                        delete(VisitorProfileSignal).where(
                            VisitorProfileSignal.tenant_id == principal.tenant_id,
                            VisitorProfileSignal.company_id == principal.company_id,
                            VisitorProfileSignal.visitor_id == principal.visitor_id,
                        )
                    )
                self._complete_idempotency(
                    claim.record,
                    resource_type="consent_record",
                    resource_id=record.id,
                    status_code=201,
                    response_body={"consent_id": str(record.id)},
                )
            profile_link_token = None
            if record.scope == ConsentScope.PROFILE_PERSONALIZATION and record.granted:
                profile_link_token, _ = self._issue_profile_link(record)
            return ConsentRecordSchema(
                id=record.id,
                scope=record.scope.value,
                policy_version=record.policy_version,
                granted=record.granted,
                recorded_at=record.recorded_at,
                profile_link_token=profile_link_token,
            )

    async def create_conversation(
        self,
        *,
        slug: str,
        principal: VisitorPrincipal,
        request: CreateConversationRequest,
        idempotency_key: str,
    ) -> ConversationRecord:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal, card_slug=slug)
            card = await self._require_principal_card(session, principal, slug)
            if request.chat_notice_version != _policy_version(card, ConsentScope.CHAT_NOTICE):
                raise _policy_version_mismatch()
            await self._require_current_consent(
                session,
                principal=principal,
                card=card,
                scope=ConsentScope.CHAT_NOTICE,
            )

            claim = await self._claim_idempotency(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                scope=f"public.conversation:{principal.visitor_id}",
                key=idempotency_key,
                request_hash=canonical_request_hash("create_conversation", request.model_dump()),
            )
            if claim.replay:
                if claim.record.resource_id is None:
                    raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "请求仍在处理中")
                conversation = await session.get(Conversation, claim.record.resource_id)
                if conversation is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等记录已失效，请重新请求")
            else:
                conversation = Conversation(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    card_id=principal.card_id,
                    visitor_id=principal.visitor_id,
                    visit_id=principal.visit_id,
                    status=ConversationStatus.ACTIVE,
                )
                session.add(conversation)
                await session.flush()
                self._complete_idempotency(
                    claim.record,
                    resource_type="conversation",
                    resource_id=conversation.id,
                    status_code=201,
                    response_body={"conversation_id": str(conversation.id)},
                )
            return ConversationRecord(
                id=conversation.id,
                status=conversation.status.value,
                created_at=conversation.started_at,
            )

    async def prepare_message(
        self,
        *,
        conversation_id: uuid.UUID,
        principal: VisitorPrincipal,
        content: str,
        idempotency_key: str,
    ) -> PreparedMessage:
        redaction = redact_sensitive_text(content.strip())
        normalized_content = redaction.content
        if not normalized_content:
            raise ApiError(400, "VALIDATION_ERROR", "问题不能为空")
        if len(normalized_content) > self._settings.max_message_chars:
            raise ApiError(400, "VALIDATION_ERROR", "问题长度超过限制")

        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            conversation = await self._require_conversation(
                session, conversation_id=conversation_id, principal=principal
            )
            card = await session.get(Card, principal.card_id)
            if (
                card is None
                or card.tenant_id != principal.tenant_id
                or card.company_id != principal.company_id
                or card.status != ContentStatus.PUBLISHED
                or card.deleted_at is not None
            ):
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
            await self._require_current_consent(
                session,
                principal=principal,
                card=card,
                scope=ConsentScope.CHAT_NOTICE,
            )
            claim = await self._claim_idempotency(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                scope=f"public.message:{conversation_id}",
                key=idempotency_key,
                request_hash=canonical_request_hash(
                    "create_message", {"content": normalized_content}
                ),
            )
            if claim.replay:
                if claim.record.resource_id is None:
                    raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "请求仍在处理中")
                assistant = await session.get(Message, claim.record.resource_id)
                if assistant is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等记录已失效，请重新请求")
                user_message = (
                    await session.execute(
                        select(Message).where(
                            Message.conversation_id == conversation_id,
                            Message.client_message_id == idempotency_key,
                            Message.role == MessageRole.USER,
                        )
                    )
                ).scalar_one_or_none()
                if user_message is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等记录已失效，请重新请求")
                return PreparedMessage(
                    conversation_id=conversation_id,
                    user_message_id=user_message.id,
                    assistant_message_id=assistant.id,
                    question=user_message.content,
                    idempotency_key=idempotency_key,
                    card_slug=card.slug,
                    replay=claim.record.status == IdempotencyStatus.COMPLETED,
                )

            if not claim.created and claim.record.resource_id is not None:
                assistant = await session.get(Message, claim.record.resource_id)
                user_message = (
                    await session.execute(
                        select(Message).where(
                            Message.conversation_id == conversation_id,
                            Message.client_message_id == idempotency_key,
                            Message.role == MessageRole.USER,
                        )
                    )
                ).scalar_one_or_none()
                if assistant is not None and user_message is not None:
                    assistant.status = MessageStatus.PENDING
                    assistant.content = ""
                    return PreparedMessage(
                        conversation_id=conversation_id,
                        user_message_id=user_message.id,
                        assistant_message_id=assistant.id,
                        question=user_message.content,
                        idempotency_key=idempotency_key,
                        card_slug=card.slug,
                    )

            message_count = (
                await session.execute(
                    select(func.count(Message.id)).where(
                        Message.conversation_id == conversation_id,
                        Message.role == MessageRole.USER,
                    )
                )
            ).scalar_one()
            if message_count >= self._settings.max_conversation_messages:
                raise ApiError(429, "CONVERSATION_LIMIT_REACHED", "本次对话已达到消息上限")

            user_message = Message(
                id=uuid.uuid4(),
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=normalized_content,
                status=MessageStatus.COMPLETED,
                content_redacted=redaction.redacted,
                client_message_id=idempotency_key,
            )
            assistant = Message(
                id=uuid.uuid4(),
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content="",
                status=MessageStatus.PENDING,
            )
            conversation.last_activity_at = datetime.now(UTC)
            session.add_all([user_message, assistant])
            await session.flush()
            await session.execute(
                update(VisitSummary)
                .where(
                    VisitSummary.tenant_id == principal.tenant_id,
                    VisitSummary.company_id == principal.company_id,
                    VisitSummary.conversation_id == conversation_id,
                    VisitSummary.is_current.is_(True),
                )
                .values(is_current=False, stale_at=func.now())
            )
            claim.record.resource_type = "message"
            claim.record.resource_id = assistant.id
            return PreparedMessage(
                conversation_id=conversation_id,
                user_message_id=user_message.id,
                assistant_message_id=assistant.id,
                question=normalized_content,
                idempotency_key=idempotency_key,
                card_slug=card.slug,
            )

    async def load_stored_answer(
        self,
        *,
        prepared: PreparedMessage,
        principal: VisitorPrincipal,
    ) -> StoredAnswer | None:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            message = await session.get(Message, prepared.assistant_message_id)
            if message is None or message.conversation_id != prepared.conversation_id:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "对话消息不存在")
            if message.status == MessageStatus.PENDING:
                return None
            if message.status == MessageStatus.FAILED:
                raise ApiError(503, "MODEL_UNAVAILABLE", "AI 服务暂不可用，请稍后重试")
            rows = (
                await session.execute(
                    select(MessageCitation, KnowledgeChunk)
                    .join(KnowledgeChunk, KnowledgeChunk.id == MessageCitation.chunk_id)
                    .where(MessageCitation.message_id == message.id)
                    .order_by(MessageCitation.rank)
                )
            ).all()
            citations = tuple(
                StoredCitation(
                    id=citation.id,
                    label=chunk.title,
                    source_type=chunk.source_type,
                )
                for citation, chunk in rows
            )
            finish_reason: Literal["stop", "refusal", "length", "content_filter"] = (
                "refusal" if message.status == MessageStatus.REFUSED else "stop"
            )
            return StoredAnswer(
                message_id=message.id,
                text=message.content,
                finish_reason=finish_reason,
                citations=citations,
                lead_prompt=(
                    prepared.card_slug != "tuotu" and _looks_like_opportunity(prepared.question)
                ),
            )

    async def assert_model_budget(self, *, principal: VisitorPrincipal) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            spent = (
                await session.execute(
                    select(func.coalesce(func.sum(AIRun.estimated_cost_cny), 0)).where(
                        AIRun.company_id == principal.company_id,
                        AIRun.created_at >= func.date_trunc("day", func.now()),
                    )
                )
            ).scalar_one()
        if Decimal(spent) >= Decimal(str(self._settings.model_daily_budget_cny)):
            raise ApiError(
                429,
                "MODEL_BUDGET_EXCEEDED",
                "今日 AI 服务额度已用完，请联系企业工作人员",
            )

    async def ensure_ai_configuration(
        self,
        *,
        principal: VisitorPrincipal,
        runtime_settings: Settings,
        profile_id: uuid.UUID | None,
    ) -> None:
        """Provision the persistence metadata required by the active Chat runtime.

        WeCom self-service enterprises are created without a tenant-specific
        prompt/model row.  The model could therefore stream a complete answer and
        only fail when ``persist_ai_answer`` tried to resolve those rows.  Keep this
        preflight before the provider call so a visitor never sees an answer followed
        by a contradictory configuration error.
        """

        prompt = PromptRegistry().get(DEFAULT_PROMPT_VERSION)
        prompt_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{principal.company_id}:rag-prompt:{prompt.version}",
        )
        model_config_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{principal.company_id}:chat:{runtime_settings.llm_provider}",
        )
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            card = await session.get(Card, principal.card_id)
            if (
                card is None
                or card.tenant_id != principal.tenant_id
                or card.company_id != principal.company_id
            ):
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
            publisher_id = card.responsible_user_id or card.owner_user_id
            if publisher_id is None:
                publisher_id = await session.scalar(
                    select(Membership.user_id)
                    .where(
                        Membership.tenant_id == principal.tenant_id,
                        Membership.company_id == principal.company_id,
                        Membership.status == LifecycleStatus.ACTIVE,
                    )
                    .order_by(Membership.created_at, Membership.id)
                    .limit(1)
                )
            if publisher_id is None:
                raise ApiError(
                    503,
                    "AI_CONFIGURATION_MISSING",
                    "企业 AI 配置尚未完成，请联系管理员",
                )

            await session.execute(
                pg_insert(PromptVersion)
                .values(
                    id=prompt_id,
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    name=prompt.version,
                    purpose="rag_answer",
                    version_number=1,
                    content=prompt.system_text,
                    content_hash=hashlib.sha256(
                        prompt.system_text.encode("utf-8")
                    ).hexdigest(),
                    change_summary="Auto-provisioned for the active enterprise AI runtime",
                    evaluation_result={"status": "requires_pilot_evaluation"},
                    status=PromptStatus.PUBLISHED,
                    published_by=publisher_id,
                    published_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(constraint="uq_prompt_versions_name_version")
            )
            await session.execute(
                pg_insert(ModelConfig)
                .values(
                    id=model_config_id,
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    purpose="chat",
                    provider=runtime_settings.llm_provider,
                    model_name=runtime_settings.llm_model,
                    endpoint_region=None,
                    secret_ref=(
                        f"platform-llm-profile:{profile_id}"
                        if profile_id is not None
                        else "environment-variable:LLM_API_KEY"
                    ),
                    timeout_ms=round(runtime_settings.llm_timeout_seconds * 1_000),
                    max_retries=runtime_settings.llm_max_retries,
                    max_concurrency=runtime_settings.llm_max_concurrency,
                    daily_budget_cny=Decimal(
                        str(runtime_settings.model_daily_budget_cny)
                    ),
                    data_retention="no_training",
                    enabled=True,
                    parameters={
                        "thinking": runtime_settings.llm_thinking,
                        "reasoning_effort": runtime_settings.llm_reasoning_effort,
                        "temperature": runtime_settings.llm_temperature,
                        "max_tokens": runtime_settings.llm_max_output_tokens,
                    },
                )
                .on_conflict_do_update(
                    constraint="uq_model_configs_purpose_provider",
                    set_={
                        "model_name": runtime_settings.llm_model,
                        "secret_ref": (
                            f"platform-llm-profile:{profile_id}"
                            if profile_id is not None
                            else "environment-variable:LLM_API_KEY"
                        ),
                        "timeout_ms": round(
                            runtime_settings.llm_timeout_seconds * 1_000
                        ),
                        "max_retries": runtime_settings.llm_max_retries,
                        "max_concurrency": runtime_settings.llm_max_concurrency,
                        "daily_budget_cny": Decimal(
                            str(runtime_settings.model_daily_budget_cny)
                        ),
                        "enabled": True,
                        "parameters": {
                            "thinking": runtime_settings.llm_thinking,
                            "reasoning_effort": runtime_settings.llm_reasoning_effort,
                            "temperature": runtime_settings.llm_temperature,
                            "max_tokens": runtime_settings.llm_max_output_tokens,
                        },
                    },
                )
            )

    async def load_forbidden_topic_rules(
        self,
        *,
        principal: VisitorPrincipal,
    ) -> tuple[ForbiddenTopicPolicy, ...]:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            rows = (
                await session.scalars(
                    select(ForbiddenTopic)
                    .where(
                        ForbiddenTopic.tenant_id == principal.tenant_id,
                        ForbiddenTopic.company_id == principal.company_id,
                        ForbiddenTopic.is_active.is_(True),
                    )
                    .order_by(ForbiddenTopic.updated_at.desc(), ForbiddenTopic.id)
                    .limit(200)
                )
            ).all()
        return tuple(
            ForbiddenTopicPolicy(
                rule_id=str(row.id),
                topic=row.topic,
                match_terms=tuple(row.match_terms),
                action=row.action,
                safe_response=(
                    redact_sensitive_text(row.safe_response).content if row.safe_response else None
                ),
                version=row.version,
            )
            for row in rows
        )

    async def load_conversation_history(
        self,
        *,
        prepared: PreparedMessage,
        principal: VisitorPrincipal,
        limit: int = 8,
    ) -> tuple[ChatMessage, ...]:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            rows = (
                (
                    await session.execute(
                        select(Message)
                        .where(
                            Message.conversation_id == prepared.conversation_id,
                            Message.id != prepared.user_message_id,
                            Message.role.in_([MessageRole.USER, MessageRole.ASSISTANT]),
                            Message.status.in_([MessageStatus.COMPLETED, MessageStatus.REFUSED]),
                            Message.content != "",
                        )
                        # User and assistant rows are inserted in one transaction and
                        # therefore usually share the exact same database timestamp.
                        # UUID ordering is random, so make the reverse-chronological
                        # query return assistant before user; reversing the result
                        # below then always restores user -> assistant turn order.
                        .order_by(
                            Message.created_at.desc(),
                            case(
                                (Message.role == MessageRole.ASSISTANT, 1),
                                else_=0,
                            ).desc(),
                            Message.id.desc(),
                        )
                        .limit(max(0, min(limit, 8)))
                    )
                )
                .scalars()
                .all()
            )
        return tuple(
            ChatMessage(role=item.role.value, content=item.content[:600]) for item in reversed(rows)
        )

    async def persist_ai_answer(
        self,
        *,
        prepared: PreparedMessage,
        principal: VisitorPrincipal,
        result: AIAnswer,
    ) -> StoredAnswer:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            assistant = await session.get(
                Message, prepared.assistant_message_id, with_for_update=True
            )
            if assistant is None or assistant.conversation_id != prepared.conversation_id:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "对话消息不存在")
            if assistant.status != MessageStatus.PENDING:
                stored = await self._stored_answer_in_session(session, assistant)
                if stored is None:
                    raise ApiError(503, "MODEL_UNAVAILABLE", "AI 服务暂不可用，请稍后重试")
                return stored

            prompt_version = (
                await session.execute(
                    select(PromptVersion)
                    .where(
                        PromptVersion.name == result.trace.prompt_version,
                        PromptVersion.status == PromptStatus.PUBLISHED,
                    )
                    .order_by(PromptVersion.version_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            model_config = (
                await session.execute(
                    select(ModelConfig)
                    .where(
                        ModelConfig.purpose == "chat",
                        ModelConfig.provider == result.trace.chat_provider,
                        ModelConfig.model_name == result.trace.chat_model,
                        ModelConfig.enabled.is_(True),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if prompt_version is None or model_config is None:
                raise ApiError(
                    503,
                    "AI_CONFIGURATION_MISSING",
                    "企业 AI 配置尚未完成，请联系管理员",
                )

            if result.refusal is None:
                visible_text = result.answer
                message_status = MessageStatus.COMPLETED
                finish_reason: Literal["stop", "refusal", "length", "content_filter"] = "stop"
            else:
                visible_text = result.refusal.reason
                if result.refusal.safe_alternative:
                    visible_text = f"{visible_text} {result.refusal.safe_alternative}".strip()
                message_status = MessageStatus.REFUSED
                finish_reason = "refusal"

            assistant.content = visible_text
            assistant.status = message_status
            output_hash = hashlib.sha256(visible_text.encode("utf-8")).hexdigest()
            ai_run = AIRun(
                id=uuid.uuid4(),
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                message_id=assistant.id,
                prompt_version_id=prompt_version.id,
                model_config_id=model_config.id,
                provider=result.trace.chat_provider,
                model=result.trace.chat_model,
                endpoint_region=model_config.endpoint_region,
                trace_id=result.trace.trace_id,
                input_hash=hashlib.sha256(prepared.question.encode("utf-8")).hexdigest(),
                output_hash=output_hash,
                input_tokens=result.trace.input_tokens,
                output_tokens=result.trace.output_tokens,
                total_latency_ms=result.trace.elapsed_ms,
                estimated_cost_cny=self._estimate_cost_cny(
                    result.trace.input_tokens,
                    result.trace.output_tokens,
                ),
                retry_count=0,
                status=message_status,
                safety_result={
                    "policy_flags": list(result.trace.policy_flags),
                    "refusal_code": result.refusal.code.value if result.refusal else None,
                    "needs_human_review": bool(result.trace.extra.get("needs_human_review", False)),
                },
                retrieval_result={
                    "mode": result.trace.retrieval_mode,
                    "count": result.trace.retrieval_count,
                    "citation_count": result.trace.citation_count,
                    "query_complexity": result.trace.extra.get(
                        "query_complexity", "not_applicable"
                    ),
                    "subquery_count": int(result.trace.extra.get("subquery_count", 0)),
                    "covered_subquery_count": int(
                        result.trace.extra.get("covered_subquery_count", 0)
                    ),
                    "uncovered_subquery_count": int(
                        result.trace.extra.get("uncovered_subquery_count", 0)
                    ),
                    "coverage_ratio": float(
                        result.trace.extra.get("retrieval_coverage_ratio", 1.0)
                    ),
                    "confidence_band": result.trace.extra.get("confidence_band", "not_applicable"),
                    "evidence_ids": list(result.trace.extra.get("retrieved_evidence_ids", ())),
                    "version_ids": list(result.trace.extra.get("retrieved_version_ids", ())),
                },
                error_code=result.trace.error_category,
                completed_at=datetime.now(UTC),
            )
            session.add(ai_run)

            stored_citations: list[StoredCitation] = []
            for rank, citation in enumerate(result.citations, start=1):
                try:
                    chunk_id = uuid.UUID(citation.evidence_id)
                except ValueError as exc:
                    raise ApiError(503, "INVALID_MODEL_OUTPUT", "AI 引用校验失败") from exc
                citation_row = MessageCitation(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    message_id=assistant.id,
                    chunk_id=chunk_id,
                    rank=rank,
                    score=max(-1.0, min(float(citation.score), 1.0)),
                    snapshot_text=citation.excerpt,
                    snapshot_hash=citation.content_hash
                    or hashlib.sha256(citation.excerpt.encode("utf-8")).hexdigest(),
                )
                session.add(citation_row)
                stored_citations.append(
                    StoredCitation(
                        id=citation_row.id,
                        label=citation.title,
                        source_type="knowledge",
                    )
                )

            claim = (
                await session.execute(
                    select(IdempotencyKey)
                    .where(
                        IdempotencyKey.scope == f"public.message:{prepared.conversation_id}",
                        IdempotencyKey.key == prepared.idempotency_key,
                    )
                    .with_for_update()
                )
            ).scalar_one()
            self._complete_idempotency(
                claim,
                resource_type="message",
                resource_id=assistant.id,
                status_code=200,
                response_body={
                    "message_id": str(assistant.id),
                    "finish_reason": finish_reason,
                },
            )

            # Every answer that cannot be grounded should become an auditable
            # knowledge-operations item. Policy refusals are deliberately not
            # knowledge gaps: adding material must never bypass a forbidden-topic rule.
            if result.refusal and result.refusal.code != RefusalCode.FORBIDDEN_TOPIC:
                await self._upsert_knowledge_gap(
                    session,
                    principal=principal,
                    conversation_id=prepared.conversation_id,
                    question=prepared.question,
                    reason=result.refusal.code.value,
                    trace_id=result.trace.trace_id,
                )

            return StoredAnswer(
                message_id=assistant.id,
                text=visible_text,
                finish_reason=finish_reason,
                citations=tuple(stored_citations),
                # A visitor's commercial intent remains actionable even when the
                # knowledge base cannot ground an AI answer.  The lead form is the
                # safe human handoff for exactly that case.
                lead_prompt=(
                    prepared.card_slug != "tuotu" and _looks_like_opportunity(prepared.question)
                ),
            )

    async def load_company_name(self, *, principal: VisitorPrincipal) -> str:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            company = await session.get(Company, principal.company_id)
            if (
                company is None
                or company.tenant_id != principal.tenant_id
                or company.deleted_at is not None
            ):
                raise ApiError(404, "RESOURCE_NOT_FOUND", "企业不存在")
            return company.name

    async def persist_ai_failure(
        self,
        *,
        prepared: PreparedMessage,
        principal: VisitorPrincipal,
        error_code: str,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            assistant = await session.get(
                Message, prepared.assistant_message_id, with_for_update=True
            )
            if assistant is not None and assistant.status == MessageStatus.PENDING:
                assistant.status = MessageStatus.FAILED
                assistant.content = ""
                await self._upsert_knowledge_gap(
                    session,
                    principal=principal,
                    conversation_id=prepared.conversation_id,
                    question=prepared.question,
                    reason=f"runtime_{error_code[:60].casefold()}",
                    trace_id=None,
                )
            claim = (
                await session.execute(
                    select(IdempotencyKey)
                    .where(
                        IdempotencyKey.scope == f"public.message:{prepared.conversation_id}",
                        IdempotencyKey.key == prepared.idempotency_key,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if claim is not None and claim.status == IdempotencyStatus.PROCESSING:
                claim.status = IdempotencyStatus.FAILED
                claim.response_status_code = 503
                claim.response_body = {"error_code": error_code}
                claim.locked_until = None

    async def _resolve_public_card(self, session: AsyncSession, slug: str) -> CardScope:
        normalized_slug = slug.strip().lower()
        if not (3 <= len(normalized_slug) <= 96):
            raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
        await session.execute(
            text("SELECT set_config('app.card_slug', :slug, true)"),
            {"slug": normalized_slug},
        )
        card = (
            await session.execute(
                select(Card).where(
                    Card.slug == normalized_slug,
                    Card.status == ContentStatus.PUBLISHED,
                    Card.deleted_at.is_(None),
                    Card.published_at.is_not(None),
                    Card.published_at <= func.now(),
                )
            )
        ).scalar_one_or_none()
        if card is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
        await self._set_scope(
            session,
            tenant_id=card.tenant_id,
            company_id=card.company_id,
            card_slug=normalized_slug,
        )
        return CardScope(
            card_id=card.id,
            tenant_id=card.tenant_id,
            company_id=card.company_id,
            slug=normalized_slug,
        )

    async def _set_principal_scope(
        self,
        session: AsyncSession,
        principal: VisitorPrincipal,
        *,
        card_slug: str | None = None,
    ) -> None:
        await self._set_scope(
            session,
            tenant_id=principal.tenant_id,
            company_id=principal.company_id,
            card_slug=card_slug,
        )

    async def _valid_profile_link_consent(
        self,
        session: AsyncSession,
        *,
        token: str | None,
        scope: CardScope,
        expected_policy: str,
    ) -> ConsentRecord | None:
        """Resolve a long-lived link without disclosing why an untrusted token failed."""
        if not token:
            return None
        try:
            principal = decode_profile_link_token(
                token,
                signing_key=self._settings.jwt_signing_key.get_secret_value(),
                issuer=self._settings.app_name,
            )
        except ProfileLinkTokenError:
            return None
        if principal.tenant_id != scope.tenant_id or principal.company_id != scope.company_id:
            return None
        latest = await session.scalar(
            select(ConsentRecord)
            .where(
                ConsentRecord.tenant_id == scope.tenant_id,
                ConsentRecord.company_id == scope.company_id,
                ConsentRecord.visitor_id == principal.visitor_id,
                ConsentRecord.scope == ConsentScope.PROFILE_PERSONALIZATION,
            )
            .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
            .limit(1)
        )
        if latest is None or latest.id != principal.consent_id or not latest.granted:
            return None
        expires_at = latest.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if (
            latest.policy_version != expected_policy
            or expires_at is None
            or expires_at <= datetime.now(UTC)
        ):
            return None
        visitor = await session.scalar(
            select(Visitor.id).where(
                Visitor.id == principal.visitor_id,
                Visitor.tenant_id == scope.tenant_id,
                Visitor.company_id == scope.company_id,
            )
        )
        return latest if visitor is not None else None

    @staticmethod
    async def _latest_profile_consent(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        visitor_id: uuid.UUID,
    ) -> ConsentRecord | None:
        return await session.scalar(
            select(ConsentRecord)
            .where(
                ConsentRecord.tenant_id == tenant_id,
                ConsentRecord.company_id == company_id,
                ConsentRecord.visitor_id == visitor_id,
                ConsentRecord.scope == ConsentScope.PROFILE_PERSONALIZATION,
            )
            .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
            .limit(1)
        )

    def _issue_profile_link(self, consent: ConsentRecord) -> tuple[str, int]:
        return issue_profile_link_token(
            signing_key=self._settings.jwt_signing_key.get_secret_value(),
            issuer=self._settings.app_name,
            ttl_seconds=self._settings.profile_link_token_ttl_seconds,
            visitor_id=consent.visitor_id,
            tenant_id=consent.tenant_id,
            company_id=consent.company_id,
            consent_id=consent.id,
        )

    @staticmethod
    async def _lock_profile_visitor(session: AsyncSession, visitor_id: uuid.UUID) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:visitor_id, 0))"),
            {"visitor_id": str(visitor_id)},
        )

    @staticmethod
    async def _set_scope(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        card_slug: str | None,
    ) -> None:
        await session.execute(
            text(
                """
                SELECT
                    set_config('app.tenant_id', :tenant_id, true),
                    set_config('app.company_id', :company_id, true),
                    set_config('app.card_slug', :card_slug, true)
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "company_id": str(company_id),
                "card_slug": card_slug or "",
            },
        )

    @staticmethod
    async def _require_principal_card(
        session: AsyncSession,
        principal: VisitorPrincipal,
        slug: str,
    ) -> Card:
        card = (
            await session.execute(
                select(Card).where(
                    Card.id == principal.card_id,
                    Card.tenant_id == principal.tenant_id,
                    Card.company_id == principal.company_id,
                    Card.slug == slug.strip().lower(),
                    Card.status == ContentStatus.PUBLISHED,
                    Card.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if card is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
        return card

    @staticmethod
    async def _require_current_consent(
        session: AsyncSession,
        *,
        principal: VisitorPrincipal,
        card: Card,
        scope: ConsentScope,
    ) -> ConsentRecord:
        consent = (
            await session.execute(
                select(ConsentRecord)
                .where(
                    ConsentRecord.tenant_id == principal.tenant_id,
                    ConsentRecord.company_id == principal.company_id,
                    ConsentRecord.visitor_id == principal.visitor_id,
                    ConsentRecord.scope == scope,
                    ConsentRecord.evidence["card_id"].as_string() == str(principal.card_id),
                )
                .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        expires_at = consent.expires_at if consent is not None else None
        evidence = (
            consent.evidence if consent is not None and isinstance(consent.evidence, dict) else {}
        )
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if (
            consent is None
            or consent.tenant_id != principal.tenant_id
            or consent.company_id != principal.company_id
            or consent.visitor_id != principal.visitor_id
            or evidence.get("card_id") != str(principal.card_id)
            or not consent.granted
            or consent.policy_version != _policy_version(card, scope)
            or (expires_at is not None and expires_at <= now)
        ):
            raise ApiError(403, "CONSENT_REQUIRED", "请先确认当前版本的授权告知")
        return consent

    @staticmethod
    async def _require_conversation(
        session: AsyncSession,
        *,
        conversation_id: uuid.UUID,
        principal: VisitorPrincipal,
    ) -> Conversation:
        conversation = (
            await session.execute(
                select(Conversation)
                .where(
                    Conversation.id == conversation_id,
                    Conversation.tenant_id == principal.tenant_id,
                    Conversation.company_id == principal.company_id,
                    Conversation.card_id == principal.card_id,
                    Conversation.visitor_id == principal.visitor_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if conversation is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "对话不存在")
        if conversation.status != ConversationStatus.ACTIVE:
            raise ApiError(422, "STATE_TRANSITION_INVALID", "对话已结束，请重新发起")
        return conversation

    @staticmethod
    async def _claim_idempotency(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        scope: str,
        key: str,
        request_hash: str,
    ) -> IdempotencyClaim:
        now = datetime.now(UTC)
        record_id = uuid.uuid4()
        inserted_id = (
            await session.execute(
                pg_insert(IdempotencyKey)
                .values(
                    id=record_id,
                    tenant_id=tenant_id,
                    company_id=company_id,
                    scope=scope,
                    key=key,
                    request_hash=request_hash,
                    status=IdempotencyStatus.PROCESSING,
                    locked_until=now + timedelta(minutes=2),
                    expires_at=now + timedelta(hours=24),
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        IdempotencyKey.tenant_id,
                        IdempotencyKey.company_id,
                        IdempotencyKey.scope,
                        IdempotencyKey.key,
                    ]
                )
                .returning(IdempotencyKey.id)
            )
        ).scalar_one_or_none()
        if inserted_id is not None:
            record = await session.get(IdempotencyKey, inserted_id)
            assert record is not None
            return IdempotencyClaim(record=record, created=True, replay=False)

        record = (
            await session.execute(
                select(IdempotencyKey)
                .where(
                    IdempotencyKey.tenant_id == tenant_id,
                    IdempotencyKey.company_id == company_id,
                    IdempotencyKey.scope == scope,
                    IdempotencyKey.key == key,
                )
                .with_for_update()
            )
        ).scalar_one()
        if not hmac.compare_digest(record.request_hash, request_hash):
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "相同幂等标识对应了不同请求")
        if record.status == IdempotencyStatus.COMPLETED:
            return IdempotencyClaim(record=record, created=False, replay=True)
        if record.status == IdempotencyStatus.PROCESSING and record.locked_until:
            locked_until = record.locked_until
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=UTC)
            if locked_until > now:
                raise ApiError(
                    409,
                    "IDEMPOTENCY_IN_PROGRESS",
                    "请求仍在处理中",
                    headers={"Retry-After": "2"},
                )
        record.status = IdempotencyStatus.PROCESSING
        record.locked_until = now + timedelta(minutes=2)
        record.response_status_code = None
        record.response_body = None
        return IdempotencyClaim(record=record, created=False, replay=False)

    @staticmethod
    def _complete_idempotency(
        record: IdempotencyKey,
        *,
        resource_type: str,
        resource_id: uuid.UUID,
        status_code: int,
        response_body: dict[str, Any],
    ) -> None:
        record.status = IdempotencyStatus.COMPLETED
        record.resource_type = resource_type
        record.resource_id = resource_id
        record.response_status_code = status_code
        record.response_body = response_body
        record.locked_until = None

    async def _stored_answer_in_session(
        self,
        session: AsyncSession,
        message: Message,
    ) -> StoredAnswer | None:
        if message.status in {MessageStatus.PENDING, MessageStatus.FAILED}:
            return None
        rows = (
            await session.execute(
                select(MessageCitation, KnowledgeChunk)
                .join(KnowledgeChunk, KnowledgeChunk.id == MessageCitation.chunk_id)
                .where(MessageCitation.message_id == message.id)
                .order_by(MessageCitation.rank)
            )
        ).all()
        citations = tuple(
            StoredCitation(
                id=citation.id,
                label=chunk.title,
                source_type=chunk.source_type,
            )
            for citation, chunk in rows
        )
        finish_reason: Literal["stop", "refusal", "length", "content_filter"] = (
            "refusal" if message.status == MessageStatus.REFUSED else "stop"
        )
        return StoredAnswer(
            message_id=message.id,
            text=message.content,
            finish_reason=finish_reason,
            citations=citations,
        )

    @staticmethod
    async def _upsert_knowledge_gap(
        session: AsyncSession,
        *,
        principal: VisitorPrincipal,
        conversation_id: uuid.UUID,
        question: str,
        reason: str,
        trace_id: str,
    ) -> None:
        normalized = "".join(question.lower().split())
        question_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        existing = (
            await session.execute(
                select(KnowledgeGap)
                .where(
                    KnowledgeGap.company_id == principal.company_id,
                    KnowledgeGap.normalized_question_hash == question_hash,
                    KnowledgeGap.status.in_(
                        [KnowledgeGapStatus.PENDING, KnowledgeGapStatus.DRAFTED]
                    ),
                )
                .order_by(KnowledgeGap.last_seen_at.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                KnowledgeGap(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    conversation_id=conversation_id,
                    normalized_question_hash=question_hash,
                    question=question,
                    reason=reason,
                    status=KnowledgeGapStatus.PENDING,
                    occurrence_count=1,
                    evidence={"trace_id": trace_id},
                )
            )
        else:
            existing.occurrence_count += 1
            existing.last_seen_at = datetime.now(UTC)
            existing.evidence = {**existing.evidence, "latest_trace_id": trace_id}

    def _anonymous_visitor_hash(
        self,
        company_id: uuid.UUID,
        visitor_id: uuid.UUID,
    ) -> str:
        return hmac.new(
            self._settings.jwt_signing_key.get_secret_value().encode("utf-8"),
            f"{company_id}:{visitor_id}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()

    def _estimate_cost_cny(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        input_cost = (
            Decimal(input_tokens)
            * Decimal(str(self._settings.llm_input_price_cny_per_million))
            / million
        )
        output_cost = (
            Decimal(output_tokens)
            * Decimal(str(self._settings.llm_output_price_cny_per_million))
            / million
        )
        return (input_cost + output_cost).quantize(Decimal("0.000001"))


async def _public_employee_identity(
    session: AsyncSession,
    *,
    card: Card,
    cipher: PiiCipher,
) -> PublicEmployeeIdentity:
    if card.owner_user_id is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "员工名片未绑定有效员工")
    row = (
        (
            await session.execute(
                select(
                    User.display_name.label("display_name"),
                    User.email_ciphertext.label("email_ciphertext"),
                    User.mobile_ciphertext.label("mobile_ciphertext"),
                    Membership.job_title.label("job_title"),
                    Membership.avatar_url.label("avatar_url"),
                    Membership.business_summary.label("business_summary"),
                )
                .join(Membership, Membership.user_id == User.id)
                .where(
                    User.id == card.owner_user_id,
                    User.status == LifecycleStatus.ACTIVE,
                    User.deleted_at.is_(None),
                    Membership.tenant_id == card.tenant_id,
                    Membership.company_id == card.company_id,
                    Membership.status == LifecycleStatus.ACTIVE,
                )
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        # Public resolution deliberately collapses inactive/out-of-scope owners
        # into the same not-found boundary as an unavailable card.
        raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在或员工身份已停用")
    return PublicEmployeeIdentity(
        display_name=str(row["display_name"]),
        job_title=_optional_string(row["job_title"]),
        avatar_url=_optional_string(row["avatar_url"]),
        business_summary=_optional_string(row["business_summary"]),
        email=(
            cipher.decrypt(row["email_ciphertext"])
            if row.get("email_ciphertext") is not None
            else None
        ),
        mobile=(
            cipher.decrypt(row["mobile_ciphertext"])
            if row.get("mobile_ciphertext") is not None
            else None
        ),
    )


def _employee_contact_fields(
    identity: PublicEmployeeIdentity,
    visibility: set[str],
) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    if "mobile" in visibility and identity.mobile:
        fields.append(
            {"label": "工作手机", "value": identity.mobile, "href": f"tel:{identity.mobile}"}
        )
    if "email" in visibility and identity.email:
        fields.append(
            {"label": "工作邮箱", "value": identity.email, "href": f"mailto:{identity.email}"}
        )
    return fields


def _employee_contact_visibility(settings: dict[str, Any]) -> set[str]:
    raw = settings.get("employee_contact_visibility")
    if raw is None:
        # Compatibility for employee cards created before explicit visibility.
        return {"mobile", "email"}
    if not isinstance(raw, list):
        return set()
    return {value for value in raw if value in {"mobile", "email"}}


def _faq_document_selection(enterprise_template: object) -> list[uuid.UUID] | None:
    """Return ordered selected ids, ``None`` for all, or ``[]`` for no FAQ block."""

    if enterprise_template is None:
        # Cards published before page templates existed keep their historical
        # behaviour and expose every currently public FAQ.
        return None
    if not isinstance(enterprise_template, dict):
        return []
    blocks = enterprise_template.get("blocks")
    if not isinstance(blocks, list):
        return []
    selected: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    has_faq = False
    for block in blocks:
        if not isinstance(block, dict) or block.get("type") != "faq":
            continue
        has_faq = True
        if block.get("faq_mode") in {None, "all_published"}:
            return None
        raw_ids = block.get("faq_document_ids")
        if not isinstance(raw_ids, list):
            continue
        for raw_id in raw_ids:
            try:
                document_id = uuid.UUID(str(raw_id))
            except (TypeError, ValueError):
                continue
            if document_id not in seen:
                seen.add(document_id)
                selected.append(document_id)
    return selected if has_faq else []


async def _public_faq_items(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    enterprise_template: object,
) -> list[PublicFaqItem]:
    """Resolve FAQ answers from current public chunks, never template body text."""

    selection = _faq_document_selection(enterprise_template)
    if selection == []:
        return []
    filters = [
        KnowledgeDocument.tenant_id == tenant_id,
        KnowledgeDocument.company_id == company_id,
        KnowledgeDocument.status == ContentStatus.PUBLISHED,
        KnowledgeDocument.source_type == "faq",
        KnowledgeDocument.current_version_id.is_not(None),
        KnowledgeChunk.tenant_id == tenant_id,
        KnowledgeChunk.company_id == company_id,
        KnowledgeChunk.version_id == KnowledgeDocument.current_version_id,
        KnowledgeChunk.is_active.is_(True),
        KnowledgeChunk.visibility == Visibility.PUBLIC,
    ]
    if selection is not None:
        filters.append(KnowledgeDocument.id.in_(selection))
    rows = (
        await session.execute(
            select(
                KnowledgeDocument.id.label("document_id"),
                KnowledgeDocument.source_id,
                KnowledgeDocument.title,
                KnowledgeChunk.text,
                KnowledgeChunk.ordinal,
                KnowledgeChunk.metadata_json,
            )
            .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(*filters)
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeChunk.ordinal)
            .limit(600)
        )
    ).all()
    faq_by_document: dict[uuid.UUID, dict[str, Any]] = {}
    encounter_order: list[uuid.UUID] = []
    for row in rows:
        document_id = uuid.UUID(str(row.document_id))
        if document_id not in faq_by_document:
            encounter_order.append(document_id)
        item = faq_by_document.setdefault(
            document_id,
            {
                "source_id": row.source_id,
                "question": row.title,
                "parts": [],
                "source_label": "企业已发布资料",
            },
        )
        item["parts"].append(row.text)
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        if isinstance(metadata.get("source_label"), str):
            item["source_label"] = metadata["source_label"]

    ordered_ids = selection if selection is not None else encounter_order
    return [
        PublicFaqItem(
            id=str(item["source_id"]),
            document_id=document_id,
            question=str(item["question"]),
            answer="\n\n".join(str(part) for part in item["parts"]),
            source_label=str(item["source_label"]),
        )
        for document_id in ordered_ids[:30]
        if (item := faq_by_document.get(document_id)) is not None
    ]


async def _public_enterprise_template(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    value: object,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    default_blocks = [
        {
            "id": "identity",
            "type": "identity",
            "visible": True,
            "directory_enabled": False,
            "sort_order": 0,
            "title": "基础名片",
        },
        {"id": "overview", "type": "rich_text", "visible": True, "sort_order": 1, "title": "概览"},
        {"id": "intro", "type": "rich_text", "visible": True, "sort_order": 2, "title": "企业介绍"},
        {
            "id": "business",
            "type": "business_collection",
            "visible": True,
            "sort_order": 3,
            "title": "核心业务",
        },
        {
            "id": "cases",
            "type": "case_collection",
            "visible": True,
            "sort_order": 4,
            "title": "代表案例",
        },
        {
            "id": "trust",
            "type": "trust_panel",
            "visible": True,
            "sort_order": 5,
            "title": "企业资料",
        },
        {"id": "faq", "type": "faq", "visible": True, "sort_order": 6, "title": "常见问题"},
        {
            "id": "ai",
            "type": "ai_assistant",
            "visible": True,
            "sort_order": 7,
            "title": "企业 AI 助手",
        },
    ]
    raw_blocks = value.get("blocks") if isinstance(value.get("blocks"), list) else []
    indexed = [(index, block) for index, block in enumerate(raw_blocks) if isinstance(block, dict)]
    merged = [
        block
        for _, block in sorted(
            indexed,
            key=lambda item: (
                item[1].get("sort_order")
                if isinstance(item[1].get("sort_order"), int)
                else item[0],
                item[0],
            ),
        )
    ]
    matched_default_ids: set[str] = set()

    def matches_default(block: dict[str, Any], default_block: dict[str, Any]) -> bool:
        return bool(
            block.get("id") == default_block["id"]
            or (default_block["type"] != "rich_text" and block.get("type") == default_block["type"])
            or (
                default_block["type"] == "rich_text"
                and block.get("type") == "rich_text"
                and block.get("title") == default_block.get("title")
            )
        )

    for index, block in enumerate(merged):
        match = next(
            (
                default_block
                for default_block in default_blocks
                if default_block["id"] not in matched_default_ids
                and matches_default(block, default_block)
            ),
            None,
        )
        if match is None:
            continue
        matched_default_ids.add(match["id"])
        if match["type"] == "identity":
            merged[index] = {
                **block,
                "visible": True,
                "directory_enabled": block.get("directory_enabled", match["directory_enabled"]),
            }

    for default_block in default_blocks:
        if default_block["id"] in matched_default_ids:
            continue
        insert_at = min(int(default_block["sort_order"]), len(merged))
        merged.insert(insert_at, default_block)
    candidate = {
        **value,
        "blocks": [{**block, "sort_order": index} for index, block in enumerate(merged)],
    }
    try:
        document = EnterpriseTemplateDocument.model_validate(candidate)
    except ValidationError:
        return None
    product_ids = {
        product_id
        for block in document.blocks
        if block.visible and block.type == "business_collection"
        for product_id in block.product_ids
    }
    public_products: dict[uuid.UUID, Product] = {}
    if product_ids:
        product_rows = (
            await session.scalars(
                select(Product).where(
                    Product.id.in_(product_ids),
                    Product.tenant_id == tenant_id,
                    Product.company_id == company_id,
                    Product.status == ContentStatus.PUBLISHED,
                    Product.visibility == Visibility.PUBLIC,
                    Product.published_at.is_not(None),
                    Product.deleted_at.is_(None),
                )
            )
        ).all()
        public_products = {row.id: row for row in product_rows}
    case_ids = {
        case_id
        for block in document.blocks
        if block.visible and block.type == "case_collection"
        for case_id in block.case_ids
    }
    public_cases: dict[uuid.UUID, CaseStudy] = {}
    if case_ids:
        case_rows = (
            await session.scalars(
                select(CaseStudy).where(
                    CaseStudy.id.in_(case_ids),
                    CaseStudy.tenant_id == tenant_id,
                    CaseStudy.company_id == company_id,
                    CaseStudy.status == ContentStatus.PUBLISHED,
                    CaseStudy.visibility == Visibility.PUBLIC,
                    CaseStudy.published_at.is_not(None),
                    CaseStudy.deleted_at.is_(None),
                )
            )
        ).all()
        public_cases = {row.id: row for row in case_rows}
    blocks: list[dict[str, Any]] = []
    for block in document.blocks:
        if not block.visible:
            continue
        asset_urls = [*block.image_urls]
        if block.video_cover_url:
            asset_urls.append(block.video_cover_url)
        if any(not _is_scoped_card_asset(url, company_id) for url in asset_urls):
            continue
        if block.type == "business_collection" and set(block.product_ids) - set(public_products):
            continue
        if block.type == "case_collection" and set(block.case_ids) - set(public_cases):
            continue
        payload = block.model_dump(mode="json")
        if block.type == "business_collection":
            payload["product_items"] = [
                {
                    "id": str(product.id),
                    "slug": product.slug,
                    "name": product.name,
                    "category": product.category,
                    "summary": product.summary,
                    "image_url": product.image_url,
                }
                for product_id in block.product_ids
                if (product := public_products.get(product_id)) is not None
            ]
        if block.type == "case_collection":
            payload["case_items"] = [
                {
                    "id": str(case_study.id),
                    "slug": case_study.slug,
                    "title": case_study.title,
                    "industry": case_study.industry,
                    "summary": case_study.result,
                    "image_url": case_study.image_url,
                }
                for case_id in block.case_ids
                if (case_study := public_cases.get(case_id)) is not None
            ]
        blocks.append(payload)
    return {
        "schema_version": document.schema_version,
        "theme_key": document.theme_key,
        "blocks": blocks,
    }


def _is_scoped_card_asset(value: str, company_id: uuid.UUID) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    try:
        index = parts.index("public")
    except ValueError:
        return False
    suffix = parts[index:]
    return (
        len(suffix) == 4
        and suffix[:2] == ["public", "card-assets"]
        and suffix[2] == str(company_id)
        and suffix[3].endswith(".webp")
    )


async def _published_enterprise_card_slug(
    session: AsyncSession,
    *,
    card: Card,
) -> str | None:
    if card.card_kind == CardKind.ENTERPRISE:
        return card.slug
    return await session.scalar(
        select(Card.slug)
        .where(
            Card.tenant_id == card.tenant_id,
            Card.company_id == card.company_id,
            Card.card_kind == CardKind.ENTERPRISE,
            Card.status == ContentStatus.PUBLISHED,
            Card.deleted_at.is_(None),
            Card.published_at.is_not(None),
            Card.published_at <= func.now(),
        )
        .order_by(Card.published_at.desc(), Card.updated_at.desc(), Card.id.asc())
        .limit(1)
    )


def _policy_version(card: Card, scope: ConsentScope) -> str:
    settings = card.settings if isinstance(card.settings, dict) else {}
    policies = settings.get("policy_versions", {})
    if not isinstance(policies, dict):
        policies = {}
    if scope == ConsentScope.BROWSE_NOTICE:
        return str(policies.get("privacy") or "privacy-v1")
    if scope == ConsentScope.CHAT_NOTICE:
        return str(policies.get("chat_notice") or "chat-notice-v1")
    if scope == ConsentScope.PROFILE_PERSONALIZATION:
        return str(policies.get("profile_personalization") or "profile-personalization-v1")
    return str(policies.get("lead_consent") or "lead-consent-v1")


def _looks_like_opportunity(question: str) -> bool:
    normalized = question.casefold()
    return any(
        marker in normalized
        for marker in (
            "报价",
            "预算",
            "采购",
            "合作",
            "演示",
            "联系",
            "方案",
            "price",
            "budget",
            "demo",
        )
    )


def _company_profile_policy(company: Company) -> str:
    settings = company.settings if isinstance(company.settings, dict) else {}
    policies = settings.get("policy_versions", {})
    if not isinstance(policies, dict):
        policies = {}
    return str(policies.get("profile_personalization") or "profile-personalization-v1")


def _policy_version_mismatch() -> ApiError:
    return ApiError(
        409,
        "POLICY_VERSION_MISMATCH",
        "授权告知已更新，请刷新页面后重新确认",
    )


def citations_to_schema(citations: tuple[StoredCitation, ...]) -> tuple[MessageCitationSchema, ...]:
    return tuple(
        MessageCitationSchema(
            citation_id=item.id,
            label=item.label,
            source_type=item.source_type,
        )
        for item in citations
    )


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _public_dict_list(
    value: object,
    *,
    allowed_keys: tuple[str, ...],
    limit: int = 12,
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            continue
        item = {
            key: raw_value.strip()
            for key in allowed_keys
            if isinstance((raw_value := raw_item.get(key)), str) and raw_value.strip()
        }
        if item:
            result.append(item)
        if len(result) >= limit:
            break
    return result
