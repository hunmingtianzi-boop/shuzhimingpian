from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import case, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.schemas import AIAnswer, ChatMessage, ForbiddenTopicPolicy, RefusalCode
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
    VisitSession,
)
from app.api.schemas import (
    ConsentRecord as ConsentRecordSchema,
)
from app.api.schemas import (
    MessageCitation as MessageCitationSchema,
)
from app.core.config import Settings
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
    Message,
    MessageCitation,
    MessageRole,
    MessageStatus,
    ModelConfig,
    PromptStatus,
    PromptVersion,
    Visibility,
    Visit,
    Visitor,
    VisitorProfileSignal,
    VisitSummary,
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
    replay: bool = False


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

    async def get_public_card(self, *, slug: str) -> PublicCard:
        async with self._sessions() as session, session.begin():
            scope = await self._resolve_public_card(session, slug)
            card = await session.get(Card, scope.card_id)
            company = await session.get(Company, scope.company_id)
            if card is None or company is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
            official_card_slug = await _published_enterprise_card_slug(
                session,
                card=card,
            )
            knowledge_count = (
                await session.execute(
                    select(func.count(KnowledgeDocument.id)).where(
                        KnowledgeDocument.company_id == company.id,
                        KnowledgeDocument.status == ContentStatus.PUBLISHED,
                        KnowledgeDocument.current_version_id.is_not(None),
                    )
                )
            ).scalar_one()

            faq_rows = (
                await session.execute(
                    select(
                        KnowledgeDocument.source_id,
                        KnowledgeDocument.title,
                        KnowledgeChunk.text,
                        KnowledgeChunk.ordinal,
                        KnowledgeChunk.metadata_json,
                    )
                    .join(
                        KnowledgeChunk,
                        KnowledgeChunk.document_id == KnowledgeDocument.id,
                    )
                    .where(
                        KnowledgeDocument.tenant_id == scope.tenant_id,
                        KnowledgeDocument.company_id == scope.company_id,
                        KnowledgeDocument.status == ContentStatus.PUBLISHED,
                        KnowledgeDocument.source_type == "faq",
                        KnowledgeChunk.version_id == KnowledgeDocument.current_version_id,
                        KnowledgeChunk.is_active.is_(True),
                        KnowledgeChunk.visibility == Visibility.PUBLIC,
                    )
                    .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeChunk.ordinal)
                    .limit(60)
                )
            ).all()
            faq_by_source: dict[str, dict[str, Any]] = {}
            for row in faq_rows:
                item = faq_by_source.setdefault(
                    row.source_id,
                    {
                        "question": row.title,
                        "parts": [],
                        "source_label": "企业已发布资料",
                    },
                )
                item["parts"].append(row.text)
                metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
                if isinstance(metadata.get("source_label"), str):
                    item["source_label"] = metadata["source_label"]

            card_settings = card.settings if isinstance(card.settings, dict) else {}
            company_settings = company.settings if isinstance(company.settings, dict) else {}
            policies = card_settings.get("policy_versions", {})
            if not isinstance(policies, dict):
                policies = {}
            suggested = card_settings.get("suggested_questions", [])
            if not isinstance(suggested, list):
                suggested = []
            suggested_questions = [str(item) for item in suggested if isinstance(item, str)][:6]
            return PublicCard(
                id=card.id,
                slug=card.slug,
                card_kind=card.card_kind,
                display_name=card.display_name,
                title=str(card_settings.get("title") or company.name),
                avatar_url=_optional_string(card_settings.get("avatar_url")),
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
                contact_fields=_public_dict_list(
                    card_settings.get("contact_fields"),
                    allowed_keys=("label", "value", "href"),
                ),
                featured_products=_public_dict_list(
                    company_settings.get("featured_products"),
                    allowed_keys=("title", "description", "url"),
                ),
                featured_cases=_public_dict_list(
                    company_settings.get("featured_cases"),
                    allowed_keys=("title", "description", "industry", "url"),
                ),
                faq_items=[
                    PublicFaqItem(
                        id=source_id,
                        question=str(item["question"]),
                        answer="\n\n".join(str(part) for part in item["parts"]),
                        source_label=str(item["source_label"]),
                    )
                    for source_id, item in list(faq_by_source.items())[:30]
                ],
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
                    profile_personalization=str(
                        _company_profile_policy(company)
                    ),
                ),
            )

    async def create_visit(
        self,
        *,
        slug: str,
        request: CreateVisitRequest,
        idempotency_key: str,
    ) -> VisitSession:
        async with self._sessions() as session, session.begin():
            scope = await self._resolve_public_card(session, slug)
            card = await session.get(Card, scope.card_id)
            company = await session.get(Company, scope.company_id)
            if card is None or company is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
            if request.privacy_notice_version != _policy_version(
                card, ConsentScope.BROWSE_NOTICE
            ):
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
                if requested_scope == ConsentScope.PROFILE_PERSONALIZATION
                and company is not None
                else _policy_version(card, requested_scope)
            )
            if request.policy_version != expected_policy:
                raise _policy_version_mismatch()
            if requested_scope == ConsentScope.PROFILE_PERSONALIZATION:
                await self._lock_profile_visitor(session, principal.visitor_id)
            if (
                request.scope == ConsentScope.PROFILE_PERSONALIZATION.value
                and request.granted
            ):
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
                if (
                    record.scope == ConsentScope.PROFILE_PERSONALIZATION
                    and not record.granted
                ):
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
            if request.chat_notice_version != _policy_version(
                card, ConsentScope.CHAT_NOTICE
            ):
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
                    redact_sensitive_text(row.safe_response).content
                    if row.safe_response
                    else None
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
        limit: int = 12,
    ) -> tuple[ChatMessage, ...]:
        async with self._sessions() as session, session.begin():
            await self._set_principal_scope(session, principal)
            rows = (
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
                    .limit(max(0, min(limit, 12)))
                )
            ).scalars().all()
        return tuple(
            ChatMessage(role=item.role.value, content=item.content[:800])
            for item in reversed(rows)
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
                lead_prompt=result.refusal is None and _looks_like_opportunity(prepared.question),
            )

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
    async def _lock_profile_visitor(
        session: AsyncSession, visitor_id: uuid.UUID
    ) -> None:
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
                    ConsentRecord.evidence["card_id"].as_string()
                    == str(principal.card_id),
                )
                .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        expires_at = consent.expires_at if consent is not None else None
        evidence = (
            consent.evidence
            if consent is not None and isinstance(consent.evidence, dict)
            else {}
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
        return str(
            policies.get("profile_personalization") or "profile-personalization-v1"
        )
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
    return str(
        policies.get("profile_personalization") or "profile-personalization-v1"
    )


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
