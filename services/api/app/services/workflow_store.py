from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, exists, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.workflow_schemas import (
    AiRunView,
    CitationView,
    ConversationDetail,
    ConversationItem,
    DailyMetric,
    DashboardOverview,
    EmployeeAnalyticsItem,
    EmployeeAnalyticsReconciliation,
    KnowledgeGapView,
    MessageView,
    NotificationView,
    OpportunityCandidateView,
    SummaryDraft,
    SummaryView,
    VisitDetail,
    VisitEventRequest,
    VisitEventView,
    VisitItem,
    VisitPageDuration,
    VisitQuestion,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import (
    AIRun,
    Card,
    CardKind,
    Company,
    ConsentRecord,
    ConsentScope,
    ContentStatus,
    Conversation,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeGap,
    KnowledgeGapStatus,
    Lead,
    LeadStatus,
    LifecycleStatus,
    Membership,
    Message,
    MessageCitation,
    MessageRole,
    MessageStatus,
    ModelConfig,
    Notification,
    PromptStatus,
    PromptVersion,
    User,
    Visit,
    VisitEvent,
    Visitor,
    VisitorProfileSignal,
    VisitorProfileSignalKind,
    VisitorProfileSignalSource,
    VisitSummary,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit
from app.services.summary_provider import (
    SUMMARY_PROMPT_VERSION,
    SUMMARY_PROMPT_VERSION_NUMBER,
    SUMMARY_SYSTEM_PROMPT,
    DeepSeekSummaryProvider,
    SummaryGeneration,
    SummaryMessage,
)

_LLM_SECRET_REFERENCE = "environment-variable:LLM_API_KEY"  # noqa: S105 - reference, not secret
_OPPORTUNITY_TERMS = (
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


@dataclass(frozen=True, slots=True)
class WorkflowScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    role: str

    @property
    def is_card_owner(self) -> bool:
        return self.role == "card_owner"


@dataclass(frozen=True, slots=True)
class PreparedSummary:
    conversation_id: uuid.UUID
    card_id: uuid.UUID
    owner_user_id: uuid.UUID
    last_message_id: uuid.UUID
    prompt_version_id: uuid.UUID
    model_config_id: uuid.UUID
    messages: tuple[SummaryMessage, ...]
    source_message_ids: tuple[uuid.UUID, ...]


@dataclass(frozen=True, slots=True)
class GapDocument:
    id: uuid.UUID
    status: ContentStatus
    current_version_id: uuid.UUID | None


class WorkflowStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        summary_provider: DeepSeekSummaryProvider | None = None,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._summary_provider = summary_provider
        self._cipher = PiiCipher.from_settings(settings)

    async def dashboard(self, *, scope: WorkflowScope, period_days: int) -> DashboardOverview:
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=period_days)
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card_filters = self._card_filters(scope)
            visit_filters = (
                Visit.tenant_id == scope.tenant_id,
                Visit.company_id == scope.company_id,
                Visit.started_at >= cutoff,
                *card_filters,
            )

            visits = int(
                await session.scalar(
                    select(func.count(Visit.id)).select_from(Visit).join(Card).where(*visit_filters)
                )
                or 0
            )
            unique_visitors = int(
                await session.scalar(
                    select(func.count(func.distinct(Visit.visitor_id)))
                    .select_from(Visit)
                    .join(Card)
                    .where(*visit_filters)
                )
                or 0
            )
            conversation_filters = (
                Conversation.tenant_id == scope.tenant_id,
                Conversation.company_id == scope.company_id,
                Conversation.started_at >= cutoff,
                *card_filters,
            )
            conversations = int(
                await session.scalar(
                    select(func.count(Conversation.id))
                    .select_from(Conversation)
                    .join(Card)
                    .where(*conversation_filters)
                )
                or 0
            )
            ai_answers = int(
                await session.scalar(
                    select(func.count(AIRun.id))
                    .select_from(AIRun)
                    .join(Message, Message.id == AIRun.message_id)
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(
                        AIRun.tenant_id == scope.tenant_id,
                        AIRun.company_id == scope.company_id,
                        AIRun.created_at >= cutoff,
                        AIRun.status.in_((MessageStatus.COMPLETED, MessageStatus.REFUSED)),
                        *card_filters,
                    )
                )
                or 0
            )
            lead_filters = (
                Lead.tenant_id == scope.tenant_id,
                Lead.company_id == scope.company_id,
                Lead.created_at >= cutoff,
                *card_filters,
            )
            new_leads = int(
                await session.scalar(
                    select(func.count(Lead.id))
                    .select_from(Lead)
                    .join(Card, Card.id == Lead.card_id)
                    .where(*lead_filters, Lead.status == LeadStatus.NEW)
                )
                or 0
            )
            total_leads = int(
                await session.scalar(
                    select(func.count(Lead.id))
                    .select_from(Lead)
                    .join(Card, Card.id == Lead.card_id)
                    .where(*lead_filters)
                )
                or 0
            )
            pending_gaps = int(
                await session.scalar(
                    select(func.count(KnowledgeGap.id))
                    .select_from(KnowledgeGap)
                    .join(Conversation, Conversation.id == KnowledgeGap.conversation_id)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(
                        KnowledgeGap.tenant_id == scope.tenant_id,
                        KnowledgeGap.company_id == scope.company_id,
                        KnowledgeGap.status.in_(
                            (KnowledgeGapStatus.PENDING, KnowledgeGapStatus.DRAFTED)
                        ),
                        *card_filters,
                    )
                )
                or 0
            )
            unread_notifications = int(
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        Notification.tenant_id == scope.tenant_id,
                        Notification.company_id == scope.company_id,
                        Notification.recipient_user_id == scope.actor_user_id,
                        Notification.read_at.is_(None),
                    )
                )
                or 0
            )

            visit_daily = await session.execute(
                select(func.date(Visit.started_at), func.count(Visit.id))
                .select_from(Visit)
                .join(Card)
                .where(*visit_filters)
                .group_by(func.date(Visit.started_at))
            )
            conversation_daily = await session.execute(
                select(func.date(Conversation.started_at), func.count(Conversation.id))
                .select_from(Conversation)
                .join(Card)
                .where(*conversation_filters)
                .group_by(func.date(Conversation.started_at))
            )
            lead_daily = await session.execute(
                select(func.date(Lead.created_at), func.count(Lead.id))
                .select_from(Lead)
                .join(Card, Card.id == Lead.card_id)
                .where(*lead_filters)
                .group_by(func.date(Lead.created_at))
            )

        visits_by_day = {row[0].isoformat(): int(row[1]) for row in visit_daily}
        conversations_by_day = {row[0].isoformat(): int(row[1]) for row in conversation_daily}
        leads_by_day = {row[0].isoformat(): int(row[1]) for row in lead_daily}
        daily = []
        for offset in range(period_days - 1, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            daily.append(
                DailyMetric(
                    day=day,
                    visits=visits_by_day.get(day, 0),
                    conversations=conversations_by_day.get(day, 0),
                    leads=leads_by_day.get(day, 0),
                )
            )
        return DashboardOverview(
            generated_at=now,
            period_days=period_days,
            visits=visits,
            unique_visitors=unique_visitors,
            conversations=conversations,
            ai_answers=ai_answers,
            total_leads=total_leads,
            new_leads=new_leads,
            pending_gaps=pending_gaps,
            unread_notifications=unread_notifications,
            conversation_rate=min(1.0, round(conversations / visits, 4)) if visits else 0,
            lead_rate=min(1.0, round(total_leads / conversations, 4)) if conversations else 0,
            daily=daily,
        )

    async def list_employee_analytics(
        self,
        *,
        scope: WorkflowScope,
        period_days: int,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
    ) -> tuple[
        list[EmployeeAnalyticsItem],
        EmployeeAnalyticsReconciliation,
        int,
        datetime,
    ]:
        generated_at = datetime.now(UTC)
        cutoff = generated_at - timedelta(days=period_days)
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card_scope = (
                Card.tenant_id == scope.tenant_id,
                Card.company_id == scope.company_id,
                Card.card_kind == CardKind.EMPLOYEE,
                Card.deleted_at.is_(None),
            )
            cards = (
                select(
                    Card.owner_user_id.label("owner_user_id"),
                    func.count(Card.id).label("card_count"),
                )
                .where(*card_scope)
                .group_by(Card.owner_user_id)
                .cte("employee_cards")
            )
            visits = (
                select(
                    Card.owner_user_id.label("owner_user_id"),
                    func.count(Visit.id).label("visits"),
                    func.count(func.distinct(Visit.visitor_id)).label("unique_visitors"),
                    func.max(Visit.started_at).label("last_visit_at"),
                )
                .select_from(Visit)
                .join(Card, Card.id == Visit.card_id)
                .where(
                    Visit.tenant_id == scope.tenant_id,
                    Visit.company_id == scope.company_id,
                    Visit.started_at >= cutoff,
                    *card_scope,
                )
                .group_by(Card.owner_user_id)
                .cte("employee_visits")
            )
            conversations = (
                select(
                    Card.owner_user_id.label("owner_user_id"),
                    func.count(Conversation.id).label("conversations"),
                    func.max(Conversation.last_activity_at).label("last_conversation_at"),
                )
                .select_from(Conversation)
                .join(Card, Card.id == Conversation.card_id)
                .where(
                    Conversation.tenant_id == scope.tenant_id,
                    Conversation.company_id == scope.company_id,
                    Conversation.started_at >= cutoff,
                    *card_scope,
                )
                .group_by(Card.owner_user_id)
                .cte("employee_conversations")
            )
            leads = (
                select(
                    Card.owner_user_id.label("owner_user_id"),
                    func.count(Lead.id).label("leads"),
                    func.max(Lead.created_at).label("last_lead_at"),
                )
                .select_from(Lead)
                .join(Card, Card.id == Lead.card_id)
                .where(
                    Lead.tenant_id == scope.tenant_id,
                    Lead.company_id == scope.company_id,
                    Lead.created_at >= cutoff,
                    *card_scope,
                )
                .group_by(Card.owner_user_id)
                .cte("employee_leads")
            )

            card_count = func.coalesce(cards.c.card_count, 0)
            visit_count = func.coalesce(visits.c.visits, 0)
            unique_count = func.coalesce(visits.c.unique_visitors, 0)
            conversation_count = func.coalesce(conversations.c.conversations, 0)
            lead_count = func.coalesce(leads.c.leads, 0)
            conversation_rate = func.coalesce(
                conversation_count * 1.0 / func.nullif(visit_count, 0), 0.0
            )
            lead_rate = func.coalesce(
                lead_count * 1.0 / func.nullif(conversation_count, 0), 0.0
            )
            last_activity = func.greatest(
                visits.c.last_visit_at,
                conversations.c.last_conversation_at,
                leads.c.last_lead_at,
            )
            filters = [
                Membership.tenant_id == scope.tenant_id,
                Membership.company_id == scope.company_id,
                Membership.status == LifecycleStatus.ACTIVE,
                User.status == LifecycleStatus.ACTIVE,
                User.deleted_at.is_(None),
            ]
            if scope.is_card_owner:
                filters.append(Membership.user_id == scope.actor_user_id)
            base = (
                select(
                    Membership,
                    User.display_name,
                    card_count.label("card_count"),
                    visit_count.label("visits"),
                    unique_count.label("unique_visitors"),
                    conversation_count.label("conversations"),
                    lead_count.label("leads"),
                    conversation_rate.label("conversation_rate"),
                    lead_rate.label("lead_rate"),
                    last_activity.label("last_activity_at"),
                )
                .join(User, User.id == Membership.user_id)
                .outerjoin(cards, cards.c.owner_user_id == Membership.user_id)
                .outerjoin(visits, visits.c.owner_user_id == Membership.user_id)
                .outerjoin(conversations, conversations.c.owner_user_id == Membership.user_id)
                .outerjoin(leads, leads.c.owner_user_id == Membership.user_id)
                .where(*filters)
            )
            total = int(
                await session.scalar(
                    select(func.count()).select_from(Membership).join(
                        User, User.id == Membership.user_id
                    ).where(*filters)
                )
                or 0
            )
            sort_columns = {
                "display_name": User.display_name,
                "card_count": card_count,
                "visits": visit_count,
                "unique_visitors": unique_count,
                "conversations": conversation_count,
                "leads": lead_count,
                "conversation_rate": conversation_rate,
                "lead_rate": lead_rate,
                "last_activity_at": last_activity,
            }
            sort_column = sort_columns[sort_by]
            ordering = sort_column.asc() if sort_order == "asc" else sort_column.desc()
            rows = (
                await session.execute(
                    base.order_by(ordering.nulls_last(), Membership.id.asc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()

            owner_filter = (
                (Card.owner_user_id == scope.actor_user_id,) if scope.is_card_owner else ()
            )
            reconciliation_row = (
                await session.execute(
                    select(
                        select(func.count(Card.id))
                        .where(*card_scope, *owner_filter)
                        .scalar_subquery(),
                        select(func.count(Visit.id))
                        .select_from(Visit)
                        .join(Card, Card.id == Visit.card_id)
                        .where(
                            Visit.tenant_id == scope.tenant_id,
                            Visit.company_id == scope.company_id,
                            Visit.started_at >= cutoff,
                            *card_scope,
                            *owner_filter,
                        )
                        .scalar_subquery(),
                        select(func.count(func.distinct(Visit.visitor_id)))
                        .select_from(Visit)
                        .join(Card, Card.id == Visit.card_id)
                        .where(
                            Visit.tenant_id == scope.tenant_id,
                            Visit.company_id == scope.company_id,
                            Visit.started_at >= cutoff,
                            *card_scope,
                            *owner_filter,
                        )
                        .scalar_subquery(),
                        select(func.coalesce(func.sum(visits.c.unique_visitors), 0))
                        .where(
                            visits.c.owner_user_id == scope.actor_user_id
                            if scope.is_card_owner
                            else text("TRUE")
                        )
                        .scalar_subquery(),
                        select(func.count(Conversation.id))
                        .select_from(Conversation)
                        .join(Card, Card.id == Conversation.card_id)
                        .where(
                            Conversation.tenant_id == scope.tenant_id,
                            Conversation.company_id == scope.company_id,
                            Conversation.started_at >= cutoff,
                            *card_scope,
                            *owner_filter,
                        )
                        .scalar_subquery(),
                        select(func.count(Lead.id))
                        .select_from(Lead)
                        .join(Card, Card.id == Lead.card_id)
                        .where(
                            Lead.tenant_id == scope.tenant_id,
                            Lead.company_id == scope.company_id,
                            Lead.created_at >= cutoff,
                            *card_scope,
                            *owner_filter,
                        )
                        .scalar_subquery(),
                        func.greatest(
                            select(func.max(Visit.started_at))
                            .select_from(Visit)
                            .join(Card, Card.id == Visit.card_id)
                            .where(
                                Visit.tenant_id == scope.tenant_id,
                                Visit.company_id == scope.company_id,
                                Visit.started_at >= cutoff,
                                *card_scope,
                                *owner_filter,
                            )
                            .scalar_subquery(),
                            select(func.max(Conversation.last_activity_at))
                            .select_from(Conversation)
                            .join(Card, Card.id == Conversation.card_id)
                            .where(
                                Conversation.tenant_id == scope.tenant_id,
                                Conversation.company_id == scope.company_id,
                                Conversation.started_at >= cutoff,
                                *card_scope,
                                *owner_filter,
                            )
                            .scalar_subquery(),
                            select(func.max(Lead.created_at))
                            .select_from(Lead)
                            .join(Card, Card.id == Lead.card_id)
                            .where(
                                Lead.tenant_id == scope.tenant_id,
                                Lead.company_id == scope.company_id,
                                Lead.created_at >= cutoff,
                                *card_scope,
                                *owner_filter,
                            )
                            .scalar_subquery(),
                        ),
                    )
                )
            ).one()

        records = [
            EmployeeAnalyticsItem(
                user_id=membership.user_id,
                membership_id=membership.id,
                display_name=display_name,
                role=membership.role.value,
                membership_status=membership.status.value,
                card_count=int(row_card_count),
                visits=int(row_visits),
                unique_visitors=int(row_unique_visitors),
                conversations=int(row_conversations),
                leads=int(row_leads),
                conversation_rate=min(1.0, round(float(row_conversation_rate), 4)),
                lead_rate=min(1.0, round(float(row_lead_rate), 4)),
                last_activity_at=row_last_activity,
            )
            for (
                membership,
                display_name,
                row_card_count,
                row_visits,
                row_unique_visitors,
                row_conversations,
                row_leads,
                row_conversation_rate,
                row_lead_rate,
                row_last_activity,
            ) in rows
        ]
        (
            total_cards,
            total_visits,
            total_unique_visitors,
            employee_unique_visitors_sum,
            total_conversations,
            total_leads,
            latest_activity,
        ) = reconciliation_row
        total_visits = int(total_visits or 0)
        total_conversations = int(total_conversations or 0)
        total_leads = int(total_leads or 0)
        reconciliation = EmployeeAnalyticsReconciliation(
            card_count=int(total_cards or 0),
            visits=total_visits,
            unique_visitors=int(total_unique_visitors or 0),
            employee_unique_visitors_sum=int(employee_unique_visitors_sum or 0),
            conversations=total_conversations,
            total_leads=total_leads,
            conversation_rate=(
                min(1.0, round(total_conversations / total_visits, 4))
                if total_visits
                else 0
            ),
            lead_rate=(
                min(1.0, round(total_leads / total_conversations, 4))
                if total_conversations
                else 0
            ),
            last_activity_at=latest_activity,
        )
        return records, reconciliation, total, generated_at

    async def list_visits(
        self,
        *,
        scope: WorkflowScope,
        limit: int,
        offset: int,
        card_id: uuid.UUID | None,
    ) -> tuple[list[VisitItem], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [
                Visit.tenant_id == scope.tenant_id,
                Visit.company_id == scope.company_id,
                *self._card_filters(scope),
            ]
            if card_id is not None:
                filters.append(Visit.card_id == card_id)
            total = int(
                await session.scalar(
                    select(func.count(Visit.id)).select_from(Visit).join(Card).where(*filters)
                )
                or 0
            )
            conversation_count = (
                select(func.count(Conversation.id))
                .where(
                    Conversation.tenant_id == Visit.tenant_id,
                    Conversation.company_id == Visit.company_id,
                    Conversation.visit_id == Visit.id,
                )
                .correlate(Visit)
                .scalar_subquery()
            )
            rows = (
                await session.execute(
                    select(Visit, Card.display_name, conversation_count)
                    .join(Card, Card.id == Visit.card_id)
                    .where(*filters)
                    .order_by(Visit.started_at.desc(), Visit.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            records = [
                VisitItem(
                    id=visit.id,
                    card_id=visit.card_id,
                    card_display_name=display_name,
                    visitor_id=visit.visitor_id,
                    source=visit.source,
                    started_at=visit.started_at,
                    ended_at=visit.ended_at,
                    duration_seconds=(
                        max(0, int((visit.ended_at - visit.started_at).total_seconds()))
                        if visit.ended_at
                        else None
                    ),
                    conversation_count=int(count or 0),
                )
                for visit, display_name, count in rows
            ]
            return records, total

    async def get_visit_detail(
        self,
        *,
        scope: WorkflowScope,
        visit_id: uuid.UUID,
    ) -> VisitDetail:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            visit_row = (
                await session.execute(
                    select(Visit, Card.display_name)
                    .join(Card, Card.id == Visit.card_id)
                    .where(
                        Visit.id == visit_id,
                        Visit.tenant_id == scope.tenant_id,
                        Visit.company_id == scope.company_id,
                        *self._card_filters(scope),
                    )
                )
            ).one_or_none()
            if visit_row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "访问记录不存在")
            visit, card_display_name = visit_row

            events = list(
                await session.scalars(
                    select(VisitEvent)
                    .where(
                        VisitEvent.visit_id == visit.id,
                        VisitEvent.tenant_id == scope.tenant_id,
                        VisitEvent.company_id == scope.company_id,
                    )
                    .order_by(VisitEvent.occurred_at, VisitEvent.id)
                )
            )
            page_totals: dict[str, dict[str, object]] = {}
            for event in events:
                metadata = event.metadata_json if isinstance(event.metadata_json, dict) else {}
                page_key = str(
                    metadata.get("page_key")
                    or event.object_id
                    or event.object_type
                    or "card"
                )[:160]
                if event.event_type not in {"page_view", "heartbeat", "leave"}:
                    continue
                current = page_totals.setdefault(
                    page_key,
                    {
                        "page_title": str(metadata.get("page_title") or page_key)[:160],
                        "object_type": event.object_type,
                        "object_id": event.object_id,
                        "duration_ms": 0.0,
                        "view_count": 0,
                        "last_viewed_at": event.occurred_at,
                    },
                )
                if event.event_type == "page_view":
                    current["view_count"] = int(current["view_count"]) + 1
                duration_ms = metadata.get("duration_ms")
                if event.event_type in {"heartbeat", "leave"} and isinstance(
                    duration_ms, (int, float)
                ):
                    current["duration_ms"] = float(current["duration_ms"]) + max(
                        0.0, min(float(duration_ms), 86_400_000.0)
                    )
                current["last_viewed_at"] = max(
                    current["last_viewed_at"], event.occurred_at
                )

            message_rows = (
                await session.execute(
                    select(Message, Conversation.id)
                    .join(
                        Conversation,
                        Conversation.id == Message.conversation_id,
                    )
                    .where(
                        Conversation.visit_id == visit.id,
                        Conversation.tenant_id == scope.tenant_id,
                        Conversation.company_id == scope.company_id,
                    )
                    .order_by(
                        Message.created_at,
                        case((Message.role == MessageRole.USER, 0), else_=1),
                        Message.id,
                    )
                )
            ).all()
            questions: list[dict[str, object]] = []
            pending_by_conversation: dict[uuid.UUID, int] = {}
            conversation_ids: set[uuid.UUID] = set()
            for message, conversation_id in message_rows:
                conversation_ids.add(conversation_id)
                if message.role == MessageRole.USER:
                    questions.append(
                        {
                            "message_id": message.id,
                            "conversation_id": conversation_id,
                            "question": message.content,
                            "asked_at": message.created_at,
                            "answer_status": None,
                        }
                    )
                    pending_by_conversation[conversation_id] = len(questions) - 1
                elif message.role == MessageRole.ASSISTANT:
                    question_index = pending_by_conversation.pop(conversation_id, None)
                    if question_index is not None:
                        questions[question_index]["answer_status"] = str(
                            getattr(message.status, "value", message.status)
                        )

            return VisitDetail(
                id=visit.id,
                card_id=visit.card_id,
                card_display_name=card_display_name,
                visitor_id=visit.visitor_id,
                source=visit.source,
                started_at=visit.started_at,
                ended_at=visit.ended_at,
                duration_seconds=(
                    max(0, int((visit.ended_at - visit.started_at).total_seconds()))
                    if visit.ended_at
                    else None
                ),
                conversation_count=len(conversation_ids),
                event_count=len(events),
                page_durations=[
                    VisitPageDuration(
                        page_key=page_key,
                        page_title=str(values["page_title"]),
                        object_type=(
                            str(values["object_type"])
                            if values["object_type"] is not None
                            else None
                        ),
                        object_id=(
                            str(values["object_id"])
                            if values["object_id"] is not None
                            else None
                        ),
                        duration_seconds=round(float(values["duration_ms"]) / 1_000, 1),
                        view_count=int(values["view_count"]),
                        last_viewed_at=values["last_viewed_at"],
                    )
                    for page_key, values in sorted(
                        page_totals.items(),
                        key=lambda item: item[1]["last_viewed_at"],
                        reverse=True,
                    )
                ],
                questions=[VisitQuestion(**question) for question in questions],
            )

    async def list_conversations(
        self,
        *,
        scope: WorkflowScope,
        limit: int,
        offset: int,
        status: str | None,
        card_id: uuid.UUID | None,
        visitor_id: uuid.UUID | None = None,
    ) -> tuple[list[ConversationItem], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [
                Conversation.tenant_id == scope.tenant_id,
                Conversation.company_id == scope.company_id,
                *self._card_filters(scope),
            ]
            if status:
                filters.append(Conversation.status == status)
            if card_id is not None:
                filters.append(Conversation.card_id == card_id)
            if visitor_id is not None:
                filters.append(Conversation.visitor_id == visitor_id)
            total = int(
                await session.scalar(
                    select(func.count(Conversation.id))
                    .select_from(Conversation)
                    .join(Card)
                    .where(*filters)
                )
                or 0
            )
            message_count = (
                select(func.count(Message.id))
                .where(Message.conversation_id == Conversation.id)
                .correlate(Conversation)
                .scalar_subquery()
            )
            has_summary = exists().where(
                VisitSummary.conversation_id == Conversation.id,
                VisitSummary.is_current.is_(True),
            )
            rows = (
                await session.execute(
                    select(Conversation, Card.display_name, message_count, has_summary)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(*filters)
                    .order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [
                self._conversation_item(conversation, display_name, count, summary)
                for conversation, display_name, count, summary in rows
            ], total

    async def get_conversation(
        self,
        *,
        scope: WorkflowScope,
        conversation_id: uuid.UUID,
        trace_id: str | None,
    ) -> ConversationDetail:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            row = (
                await session.execute(
                    select(Conversation, Card.display_name)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.tenant_id == scope.tenant_id,
                        Conversation.company_id == scope.company_id,
                        *self._card_filters(scope),
                    )
                )
            ).one_or_none()
            if row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "对话不存在或不在当前作用域")
            conversation, display_name = row
            messages = (
                await session.scalars(
                    select(Message)
                    .where(
                        Message.tenant_id == scope.tenant_id,
                        Message.company_id == scope.company_id,
                        Message.conversation_id == conversation.id,
                    )
                    .order_by(Message.created_at, Message.id)
                )
            ).all()
            message_ids = [item.id for item in messages]
            citations_by_message: dict[uuid.UUID, list[CitationView]] = {}
            runs_by_message: dict[uuid.UUID, AiRunView] = {}
            if message_ids:
                citation_rows = (
                    await session.execute(
                        select(MessageCitation, KnowledgeChunk)
                        .join(KnowledgeChunk, KnowledgeChunk.id == MessageCitation.chunk_id)
                        .where(
                            MessageCitation.tenant_id == scope.tenant_id,
                            MessageCitation.company_id == scope.company_id,
                            MessageCitation.message_id.in_(message_ids),
                        )
                        .order_by(MessageCitation.message_id, MessageCitation.rank)
                    )
                ).all()
                for citation, chunk in citation_rows:
                    citations_by_message.setdefault(citation.message_id, []).append(
                        CitationView(
                            id=citation.id,
                            chunk_id=citation.chunk_id,
                            rank=citation.rank,
                            score=citation.score,
                            title=chunk.title,
                            source_type=chunk.source_type,
                            source_id=chunk.source_id,
                            snapshot_text=citation.snapshot_text,
                        )
                    )
                runs = (
                    await session.scalars(
                        select(AIRun).where(
                            AIRun.tenant_id == scope.tenant_id,
                            AIRun.company_id == scope.company_id,
                            AIRun.message_id.in_(message_ids),
                        )
                    )
                ).all()
                runs_by_message = {
                    run.message_id: AiRunView(
                        provider=run.provider,
                        model=run.model,
                        status=run.status.value,
                        first_token_latency_ms=run.first_token_latency_ms,
                        total_latency_ms=run.total_latency_ms,
                        retrieval_result=run.retrieval_result,
                        safety_result=run.safety_result,
                        error_code=run.error_code,
                    )
                    for run in runs
                }
            summary = await session.scalar(
                select(VisitSummary).where(
                    VisitSummary.conversation_id == conversation.id,
                    VisitSummary.is_current.is_(True),
                )
            )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="conversation.sensitive_read",
                resource_type="conversation",
                resource_id=conversation.id,
                trace_id=trace_id,
                event_data={"message_count": len(messages)},
            )
            item = self._conversation_item(
                conversation,
                display_name,
                len(messages),
                summary is not None,
            )
            return ConversationDetail(
                **item.model_dump(),
                messages=[
                    MessageView(
                        id=message.id,
                        role=message.role.value,
                        content=message.content,
                        status=message.status.value,
                        content_redacted=message.content_redacted,
                        created_at=message.created_at,
                        citations=citations_by_message.get(message.id, []),
                        ai_run=runs_by_message.get(message.id),
                    )
                    for message in messages
                ],
                current_summary=self._summary_view(summary) if summary else None,
            )

    async def list_opportunities(
        self,
        *,
        scope: WorkflowScope,
        limit: int,
        offset: int,
    ) -> tuple[list[OpportunityCandidateView], int]:
        """List detectable high-intent conversations without manufacturing a lead.

        A person only becomes a lead after voluntarily submitting the contact form.
        Until then the operator receives an anonymous, auditable opportunity signal.
        """

        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            term_match = or_(*[Message.content.ilike(f"%{term}%") for term in _OPPORTUNITY_TERMS])
            high_intent_question = (
                select(Message.content)
                .where(
                    Message.tenant_id == scope.tenant_id,
                    Message.company_id == scope.company_id,
                    Message.conversation_id == Conversation.id,
                    Message.role == MessageRole.USER,
                    term_match,
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
                .correlate(Conversation)
                .scalar_subquery()
            )
            has_consented_lead = exists().where(
                Lead.tenant_id == scope.tenant_id,
                Lead.company_id == scope.company_id,
                Lead.conversation_id == Conversation.id,
            )
            filters = [
                Conversation.tenant_id == scope.tenant_id,
                Conversation.company_id == scope.company_id,
                high_intent_question.is_not(None),
                *self._card_filters(scope),
            ]
            base = select(Conversation).join(Card, Card.id == Conversation.card_id).where(*filters)
            total = int(
                await session.scalar(select(func.count()).select_from(base.subquery())) or 0
            )
            rows = (
                await session.execute(
                    select(
                        Conversation,
                        Card.display_name,
                        high_intent_question.label("question"),
                        has_consented_lead.label("has_consented_lead"),
                    )
                    .join(Card, Card.id == Conversation.card_id)
                    .where(*filters)
                    .order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [
                OpportunityCandidateView(
                    conversation_id=conversation.id,
                    card_id=conversation.card_id,
                    card_display_name=display_name,
                    visitor_id=conversation.visitor_id,
                    question=question,
                    reason=_opportunity_reason(question),
                    score=_opportunity_score(question),
                    has_consented_lead=bool(consented_lead),
                    last_activity_at=conversation.last_activity_at,
                )
                for conversation, display_name, question, consented_lead in rows
                if question
            ], total

    async def generate_summary(
        self,
        *,
        scope: WorkflowScope,
        conversation_id: uuid.UUID,
        trace_id: str | None,
    ) -> SummaryView:
        prepared, existing = await self._prepare_summary(
            scope=scope,
            conversation_id=conversation_id,
        )
        if existing is not None:
            return existing
        if self._summary_provider is None:
            raise ApiError(503, "SUMMARY_PROVIDER_UNAVAILABLE", "AI 纪要服务尚未配置")
        generation = await self._summary_provider.generate(prepared.messages, trace_id=trace_id)
        return await self._persist_summary(
            scope=scope,
            prepared=prepared,
            draft=generation.draft,
            generation=generation,
            trace_id=trace_id,
        )

    async def get_summary(
        self,
        *,
        scope: WorkflowScope,
        summary_id: uuid.UUID,
        trace_id: str | None,
    ) -> SummaryView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            summary = await session.scalar(
                select(VisitSummary)
                .join(Conversation, Conversation.id == VisitSummary.conversation_id)
                .join(Card, Card.id == Conversation.card_id)
                .where(
                    VisitSummary.id == summary_id,
                    VisitSummary.tenant_id == scope.tenant_id,
                    VisitSummary.company_id == scope.company_id,
                    *self._card_filters(scope),
                )
            )
            if summary is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "拜访纪要不存在或不在当前作用域")
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="visit_summary.read",
                resource_type="visit_summary",
                resource_id=summary.id,
                trace_id=trace_id,
                event_data={"conversation_id": summary.conversation_id},
            )
            return self._summary_view(summary)

    async def approve_summary(
        self,
        *,
        scope: WorkflowScope,
        summary_id: uuid.UUID,
        trace_id: str | None,
    ) -> SummaryView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            row = (
                await session.execute(
                    select(VisitSummary, Conversation)
                    .join(Conversation, Conversation.id == VisitSummary.conversation_id)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(
                        VisitSummary.id == summary_id,
                        VisitSummary.tenant_id == scope.tenant_id,
                        VisitSummary.company_id == scope.company_id,
                        *self._card_filters(scope),
                    )
                    .with_for_update(of=VisitSummary)
                )
            ).one_or_none()
            if row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "拜访纪要不存在或不在当前作用域")
            summary, conversation = row
            if not summary.is_current:
                raise ApiError(409, "SUMMARY_STALE", "仅当前版本纪要可以审核通过")
            if summary.approved_at is None:
                summary.approved_at = datetime.now(UTC)
                summary.approved_by = scope.actor_user_id
                await self._aggregate_profile_signals(
                    session,
                    scope=scope,
                    conversation=conversation,
                    summary=summary,
                )
                await append_audit(
                    session,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    actor_user_id=scope.actor_user_id,
                    action="visit_summary.approve",
                    resource_type="visit_summary",
                    resource_id=summary.id,
                    trace_id=trace_id,
                    event_data={"conversation_id": summary.conversation_id},
                )
                await session.flush()
            return self._summary_view(summary)

    async def list_gaps(
        self,
        *,
        scope: WorkflowScope,
        limit: int,
        offset: int,
        status: str | None,
    ) -> tuple[list[KnowledgeGapView], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [
                KnowledgeGap.tenant_id == scope.tenant_id,
                KnowledgeGap.company_id == scope.company_id,
                *self._card_filters(scope),
            ]
            if status:
                filters.append(KnowledgeGap.status == status)
            base = (
                select(KnowledgeGap)
                .join(Conversation, Conversation.id == KnowledgeGap.conversation_id)
                .join(Card, Card.id == Conversation.card_id)
                .where(*filters)
            )
            total = int(
                await session.scalar(select(func.count()).select_from(base.subquery())) or 0
            )
            rows = (
                await session.scalars(
                    base.order_by(KnowledgeGap.last_seen_at.desc(), KnowledgeGap.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [self._gap_view(gap) for gap in rows], total

    async def get_gap(
        self,
        *,
        scope: WorkflowScope,
        gap_id: uuid.UUID,
    ) -> KnowledgeGapView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            gap = await self._gap(session, scope=scope, gap_id=gap_id)
            return self._gap_view(gap)

    async def update_gap_answer(
        self,
        *,
        scope: WorkflowScope,
        gap_id: uuid.UUID,
        suggested_answer: str,
        trace_id: str | None,
    ) -> KnowledgeGapView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            gap = await self._gap(session, scope=scope, gap_id=gap_id, for_update=True)
            if gap.status in {KnowledgeGapStatus.INDEXED, KnowledgeGapStatus.INDEXING}:
                raise ApiError(409, "GAP_ALREADY_PUBLISHED", "该知识缺口已进入发布流程")
            gap.suggested_answer = suggested_answer.strip()
            gap.status = KnowledgeGapStatus.DRAFTED
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge_gap.draft",
                resource_type="knowledge_gap",
                resource_id=gap.id,
                trace_id=trace_id,
                event_data={"question_hash": gap.normalized_question_hash},
            )
            await session.flush()
            await session.refresh(gap)
            return self._gap_view(gap)

    async def reject_gap(
        self,
        *,
        scope: WorkflowScope,
        gap_id: uuid.UUID,
        trace_id: str | None,
    ) -> KnowledgeGapView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            gap = await self._gap(session, scope=scope, gap_id=gap_id, for_update=True)
            if gap.status == KnowledgeGapStatus.INDEXED:
                raise ApiError(409, "GAP_ALREADY_PUBLISHED", "已发布知识不能直接拒绝")
            gap.status = KnowledgeGapStatus.REJECTED
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge_gap.reject",
                resource_type="knowledge_gap",
                resource_id=gap.id,
                trace_id=trace_id,
                event_data={},
            )
            await session.flush()
            await session.refresh(gap)
            return self._gap_view(gap)

    async def find_gap_document(
        self, *, scope: WorkflowScope, gap_id: uuid.UUID
    ) -> GapDocument | None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._gap(session, scope=scope, gap_id=gap_id)
            document = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == scope.tenant_id,
                    KnowledgeDocument.company_id == scope.company_id,
                    KnowledgeDocument.source_type == "knowledge_gap",
                    KnowledgeDocument.source_id == str(gap_id),
                )
            )
            if document is None:
                return None
            return GapDocument(document.id, document.status, document.current_version_id)

    async def begin_gap_publish(
        self,
        *,
        scope: WorkflowScope,
        gap_id: uuid.UUID,
        trace_id: str | None,
    ) -> KnowledgeGapView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            gap = await self._gap(session, scope=scope, gap_id=gap_id, for_update=True)
            if gap.status == KnowledgeGapStatus.INDEXED:
                return self._gap_view(gap)
            if gap.status not in {
                KnowledgeGapStatus.DRAFTED,
                KnowledgeGapStatus.FAILED,
                KnowledgeGapStatus.APPROVED,
            }:
                raise ApiError(409, "GAP_NOT_REVIEWED", "请先补充并审核建议答案")
            if not gap.suggested_answer:
                raise ApiError(409, "GAP_ANSWER_REQUIRED", "请先补充建议答案")
            gap.status = KnowledgeGapStatus.INDEXING
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge_gap.publish_start",
                resource_type="knowledge_gap",
                resource_id=gap.id,
                trace_id=trace_id,
                event_data={},
            )
            await session.flush()
            await session.refresh(gap)
            return self._gap_view(gap)

    async def mark_gap_failed(
        self,
        *,
        scope: WorkflowScope,
        gap_id: uuid.UUID,
        error_code: str,
        trace_id: str | None,
    ) -> KnowledgeGapView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            gap = await self._gap(session, scope=scope, gap_id=gap_id, for_update=True)
            if gap.status != KnowledgeGapStatus.INDEXED:
                gap.status = KnowledgeGapStatus.FAILED
                gap.evidence = {**gap.evidence, "last_error_code": error_code[:80]}
                await append_audit(
                    session,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    actor_user_id=scope.actor_user_id,
                    action="knowledge_gap.publish_failed",
                    resource_type="knowledge_gap",
                    resource_id=gap.id,
                    trace_id=trace_id,
                    event_data={"error_code": error_code[:80]},
                )
                await session.flush()
                await session.refresh(gap)
            return self._gap_view(gap)

    async def mark_gap_indexed(
        self,
        *,
        scope: WorkflowScope,
        gap_id: uuid.UUID,
        version_id: uuid.UUID,
        trace_id: str | None,
    ) -> KnowledgeGapView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            gap = await self._gap(session, scope=scope, gap_id=gap_id, for_update=True)
            gap.status = KnowledgeGapStatus.INDEXED
            gap.approved_version_id = version_id
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge_gap.publish",
                resource_type="knowledge_gap",
                resource_id=gap.id,
                trace_id=trace_id,
                event_data={"version_id": version_id},
            )
            await session.flush()
            await session.refresh(gap)
            return self._gap_view(gap)

    async def list_notifications(
        self,
        *,
        scope: WorkflowScope,
        limit: int,
        unread_only: bool,
    ) -> tuple[list[NotificationView], int, int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = (
                Notification.tenant_id == scope.tenant_id,
                Notification.company_id == scope.company_id,
                Notification.recipient_user_id == scope.actor_user_id,
            )
            total = int(
                await session.scalar(select(func.count(Notification.id)).where(*filters)) or 0
            )
            unread = int(
                await session.scalar(
                    select(func.count(Notification.id)).where(
                        *filters, Notification.read_at.is_(None)
                    )
                )
                or 0
            )
            statement = select(Notification).where(*filters)
            if unread_only:
                statement = statement.where(Notification.read_at.is_(None))
            rows = (
                await session.scalars(
                    statement.order_by(
                        Notification.created_at.desc(), Notification.id.desc()
                    ).limit(limit)
                )
            ).all()
            return [self._notification_view(item) for item in rows], total, unread

    async def mark_notification_read(
        self,
        *,
        scope: WorkflowScope,
        notification_id: uuid.UUID,
    ) -> NotificationView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            notification = await session.scalar(
                select(Notification)
                .where(
                    Notification.id == notification_id,
                    Notification.tenant_id == scope.tenant_id,
                    Notification.company_id == scope.company_id,
                    Notification.recipient_user_id == scope.actor_user_id,
                )
                .with_for_update()
            )
            if notification is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "通知不存在")
            if notification.read_at is None:
                notification.read_at = datetime.now(UTC)
                await session.flush()
            return self._notification_view(notification)

    async def record_visit_event(
        self,
        *,
        slug: str,
        principal_tenant_id: uuid.UUID,
        principal_company_id: uuid.UUID,
        principal_card_id: uuid.UUID,
        principal_visitor_id: uuid.UUID,
        principal_visit_id: uuid.UUID,
        request: VisitEventRequest,
    ) -> VisitEventView:
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=principal_tenant_id,
                company_id=principal_company_id,
                card_slug=slug,
            )
            card = await session.scalar(
                select(Card).where(
                    Card.id == principal_card_id,
                    Card.tenant_id == principal_tenant_id,
                    Card.company_id == principal_company_id,
                    Card.slug == slug,
                    Card.status == ContentStatus.PUBLISHED,
                    Card.deleted_at.is_(None),
                )
            )
            visit = await session.scalar(
                select(Visit)
                .where(
                    Visit.id == principal_visit_id,
                    Visit.card_id == principal_card_id,
                    Visit.visitor_id == principal_visitor_id,
                    Visit.tenant_id == principal_tenant_id,
                    Visit.company_id == principal_company_id,
                )
                .with_for_update()
            )
            if card is None or visit is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "访问会话不存在")
            existing = await session.get(VisitEvent, request.event_id)
            if existing is not None:
                if existing.visit_id != visit.id:
                    raise ApiError(409, "EVENT_ID_CONFLICT", "事件标识已被使用")
                return VisitEventView(
                    id=existing.id,
                    event_type=existing.event_type,
                    occurred_at=existing.occurred_at,
                )
            event = VisitEvent(
                id=request.event_id,
                tenant_id=principal_tenant_id,
                company_id=principal_company_id,
                visit_id=visit.id,
                event_type=request.event_type,
                object_type=request.object_type,
                object_id=request.object_id,
                metadata_json=request.metadata,
            )
            session.add(event)
            if request.event_type == "leave":
                visit.ended_at = datetime.now(UTC)
            await session.execute(
                update(Visitor)
                .where(
                    Visitor.id == principal_visitor_id,
                    Visitor.tenant_id == principal_tenant_id,
                    Visitor.company_id == principal_company_id,
                )
                .values(last_seen_at=datetime.now(UTC))
            )
            await session.flush()
            return VisitEventView(
                id=event.id, event_type=event.event_type, occurred_at=event.occurred_at
            )

    async def _prepare_summary(
        self,
        *,
        scope: WorkflowScope,
        conversation_id: uuid.UUID,
    ) -> tuple[PreparedSummary, SummaryView | None]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            row = (
                await session.execute(
                    select(Conversation, Card)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.tenant_id == scope.tenant_id,
                        Conversation.company_id == scope.company_id,
                        *self._card_filters(scope),
                    )
                )
            ).one_or_none()
            if row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "对话不存在或不在当前作用域")
            conversation, card = row
            messages = (
                await session.scalars(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation.id,
                        Message.status.in_((MessageStatus.COMPLETED, MessageStatus.REFUSED)),
                    )
                    .order_by(Message.created_at, Message.id)
                )
            ).all()
            if not messages:
                raise ApiError(409, "SUMMARY_SOURCE_EMPTY", "对话尚无可生成纪要的消息")
            prompt = await self._summary_prompt(session, scope=scope)
            model_config = await self._summary_model_config(session, scope=scope)
            last_message = messages[-1]
            existing = await session.scalar(
                select(VisitSummary).where(
                    VisitSummary.conversation_id == conversation.id,
                    VisitSummary.last_message_id == last_message.id,
                    VisitSummary.prompt_version_id == prompt.id,
                )
            )
            prepared = PreparedSummary(
                conversation_id=conversation.id,
                card_id=card.id,
                owner_user_id=card.responsible_user_id,
                last_message_id=last_message.id,
                prompt_version_id=prompt.id,
                model_config_id=model_config.id,
                messages=tuple(
                    SummaryMessage(
                        id=str(message.id),
                        role=message.role.value,
                        content=message.content,
                    )
                    for message in messages
                ),
                source_message_ids=tuple(message.id for message in messages),
            )
            return prepared, self._summary_view(existing) if existing else None

    async def _persist_summary(
        self,
        *,
        scope: WorkflowScope,
        prepared: PreparedSummary,
        draft: SummaryDraft,
        generation: SummaryGeneration,
        trace_id: str | None,
    ) -> SummaryView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            conversation = await session.scalar(
                select(Conversation)
                .where(
                    Conversation.id == prepared.conversation_id,
                    Conversation.tenant_id == scope.tenant_id,
                    Conversation.company_id == scope.company_id,
                )
                .with_for_update()
            )
            if conversation is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "对话不存在")
            latest_message_id = await session.scalar(
                select(Message.id)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.status.in_((MessageStatus.COMPLETED, MessageStatus.REFUSED)),
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
            if latest_message_id != prepared.last_message_id:
                raise ApiError(409, "SUMMARY_SOURCE_CHANGED", "对话已更新，请重新生成纪要")
            existing = await session.scalar(
                select(VisitSummary).where(
                    VisitSummary.conversation_id == conversation.id,
                    VisitSummary.last_message_id == prepared.last_message_id,
                    VisitSummary.prompt_version_id == prepared.prompt_version_id,
                )
            )
            if existing is not None:
                return self._summary_view(existing)
            now = datetime.now(UTC)
            await session.execute(
                update(VisitSummary)
                .where(
                    VisitSummary.conversation_id == conversation.id,
                    VisitSummary.is_current.is_(True),
                )
                .values(is_current=False, stale_at=now)
            )
            summary = VisitSummary(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                conversation_id=conversation.id,
                last_message_id=prepared.last_message_id,
                prompt_version_id=prepared.prompt_version_id,
                summary=draft.summary,
                interests=draft.interests,
                strength=draft.strength,
                next_step=draft.next_step,
                risk_notes=draft.risk_notes,
                source_message_ids=list(prepared.source_message_ids),
                is_current=True,
            )
            conversation.primary_intent = (
                None if draft.primary_intent == "unknown" else draft.primary_intent
            )
            session.add(summary)
            await session.flush()
            estimated_cost = (
                generation.input_tokens * self._settings.llm_input_price_cny_per_million
                + generation.output_tokens * self._settings.llm_output_price_cny_per_million
            ) / 1_000_000
            session.add(
                AIRun(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    message_id=None,
                    purpose="visit_summary",
                    resource_type="visit_summary",
                    resource_id=summary.id,
                    prompt_version_id=prepared.prompt_version_id,
                    model_config_id=prepared.model_config_id,
                    provider=generation.provider,
                    model=generation.model,
                    trace_id=trace_id or str(uuid.uuid4()),
                    input_hash=generation.input_hash,
                    output_hash=generation.output_hash,
                    input_tokens=generation.input_tokens,
                    output_tokens=generation.output_tokens,
                    first_token_latency_ms=None,
                    total_latency_ms=generation.total_latency_ms,
                    estimated_cost_cny=estimated_cost,
                    retry_count=generation.retry_count,
                    status=MessageStatus.COMPLETED,
                    safety_result={"pii_redaction_applied": True},
                    retrieval_result={
                        "source_message_ids": [str(value) for value in prepared.source_message_ids]
                    },
                    started_at=now,
                    completed_at=now,
                )
            )
            session.add(
                Notification(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    recipient_user_id=prepared.owner_user_id,
                    notification_type="visit_summary_ready",
                    title="新拜访纪要已生成",
                    body="AI 已根据最新对话生成结构化纪要，请及时查看并人工确认。",
                    resource_type="conversation",
                    resource_id=conversation.id,
                )
            )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="visit_summary.generate",
                resource_type="visit_summary",
                resource_id=summary.id,
                trace_id=trace_id,
                event_data={
                    "conversation_id": conversation.id,
                    "last_message_id": prepared.last_message_id,
                    "prompt_version_id": prepared.prompt_version_id,
                    "source_message_count": len(prepared.source_message_ids),
                },
            )
            await session.flush()
            await session.refresh(summary)
            return self._summary_view(summary)

    async def _aggregate_profile_signals(
        self,
        session: AsyncSession,
        *,
        scope: WorkflowScope,
        conversation: Conversation,
        summary: VisitSummary,
    ) -> None:
        """Persist approved summary labels; raw message text never enters the profile."""
        if summary.approved_at is None or summary.approved_by is None:
            return
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:visitor_id, 0))"),
            {"visitor_id": str(conversation.visitor_id)},
        )
        consent = await session.scalar(
            select(ConsentRecord)
            .where(
                ConsentRecord.tenant_id == scope.tenant_id,
                ConsentRecord.company_id == scope.company_id,
                ConsentRecord.visitor_id == conversation.visitor_id,
                ConsentRecord.scope == ConsentScope.PROFILE_PERSONALIZATION,
            )
            .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
            .limit(1)
        )
        company = await session.get(Company, scope.company_id)
        if consent is None or company is None or not consent.granted:
            return
        expires_at = consent.expires_at
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        company_settings = company.settings if isinstance(company.settings, dict) else {}
        policies = company_settings.get("policy_versions", {})
        if not isinstance(policies, dict):
            policies = {}
        expected_policy = str(
            policies.get("profile_personalization") or "profile-personalization-v1"
        )
        if (
            consent.policy_version != expected_policy
            or expires_at is None
            or expires_at <= datetime.now(UTC)
        ):
            return

        interest_labels = list(
            dict.fromkeys(
                value.strip()[:160]
                for value in summary.interests
                if isinstance(value, str) and value.strip()
            )
        )
        signal_labels: list[tuple[VisitorProfileSignalKind, str]] = [
            (VisitorProfileSignalKind.INTEREST, label) for label in interest_labels
        ]
        if conversation.primary_intent:
            signal_labels.append(
                (VisitorProfileSignalKind.INTENT, conversation.primary_intent)
            )
        if not signal_labels or not summary.source_message_ids:
            return
        valid_source_ids = set(
            (
                await session.scalars(
                    select(Message.id).where(
                        Message.tenant_id == scope.tenant_id,
                        Message.company_id == scope.company_id,
                        Message.conversation_id == conversation.id,
                        Message.id.in_(summary.source_message_ids),
                    )
                )
            ).all()
        )
        if valid_source_ids != set(summary.source_message_ids):
            raise ApiError(409, "SUMMARY_SOURCE_MISMATCH", "纪要证据链与对话不匹配")
        strength = _profile_strength(summary.strength)
        observed_at = summary.created_at or datetime.now(UTC)
        retention_expires_at = min(
            expires_at,
            observed_at + timedelta(days=self._settings.visitor_profile_retention_days),
        )
        for kind, label in signal_labels:
            label_hmac = self._cipher.hmac(
                f"profile-signal:{scope.tenant_id}:{scope.company_id}:"
                f"{kind.value}:{label.casefold()}"
            )
            signal = await session.scalar(
                select(VisitorProfileSignal)
                .where(
                    VisitorProfileSignal.tenant_id == scope.tenant_id,
                    VisitorProfileSignal.company_id == scope.company_id,
                    VisitorProfileSignal.visitor_id == conversation.visitor_id,
                    VisitorProfileSignal.kind == kind,
                    VisitorProfileSignal.label_hmac == label_hmac,
                )
                .with_for_update()
            )
            if signal is None:
                signal = VisitorProfileSignal(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    visitor_id=conversation.visitor_id,
                    kind=kind,
                    label_ciphertext=self._cipher.encrypt(label),
                    label_hmac=label_hmac,
                    strength=strength,
                    confidence=strength,
                    first_seen_at=observed_at,
                    last_seen_at=observed_at,
                    evidence_count=0,
                    retention_expires_at=retention_expires_at,
                    encryption_key_ref=self._cipher.key_ref,
                )
                session.add(signal)
                await session.flush()
            added = 0
            for message_id in summary.source_message_ids:
                exists_source = await session.scalar(
                    select(VisitorProfileSignalSource.id).where(
                        VisitorProfileSignalSource.signal_id == signal.id,
                        VisitorProfileSignalSource.summary_id == summary.id,
                        VisitorProfileSignalSource.message_id == message_id,
                    )
                )
                if exists_source is not None:
                    continue
                session.add(
                    VisitorProfileSignalSource(
                        id=uuid.uuid4(),
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                        signal_id=signal.id,
                        consent_id=consent.id,
                        visit_id=conversation.visit_id,
                        conversation_id=conversation.id,
                        summary_id=summary.id,
                        message_id=message_id,
                        contribution=strength,
                        confidence=strength,
                        observed_at=observed_at,
                        retention_expires_at=retention_expires_at,
                    )
                )
                added += 1
            if added:
                signal.evidence_count += added
                signal.strength = max(signal.strength, strength)
                signal.confidence = min(1.0, max(signal.confidence, strength))
                signal.last_seen_at = max(signal.last_seen_at, observed_at)
                signal.retention_expires_at = max(
                    signal.retention_expires_at, retention_expires_at
                )

    async def _summary_prompt(
        self, session: AsyncSession, *, scope: WorkflowScope
    ) -> PromptVersion:
        prompt_hash = hashlib.sha256(SUMMARY_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        prompt_id = uuid.uuid5(uuid.NAMESPACE_URL, f"{scope.company_id}:{SUMMARY_PROMPT_VERSION}")
        await session.execute(
            pg_insert(PromptVersion)
            .values(
                id=prompt_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                name="visit-summary",
                purpose="visit_summary",
                version_number=SUMMARY_PROMPT_VERSION_NUMBER,
                content=SUMMARY_SYSTEM_PROMPT,
                content_hash=prompt_hash,
                change_summary="V2 adds a constrained primary-intent classification",
                evaluation_result={"schema": "SummaryDraft", "version": SUMMARY_PROMPT_VERSION},
                status=PromptStatus.PUBLISHED.value,
                published_by=scope.actor_user_id,
                published_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_prompt_versions_name_version")
        )
        prompt = await session.scalar(
            select(PromptVersion).where(
                PromptVersion.tenant_id == scope.tenant_id,
                PromptVersion.company_id == scope.company_id,
                PromptVersion.name == "visit-summary",
                PromptVersion.version_number == SUMMARY_PROMPT_VERSION_NUMBER,
                PromptVersion.status == PromptStatus.PUBLISHED,
            )
        )
        if prompt is None or prompt.content_hash != prompt_hash:
            raise ApiError(503, "SUMMARY_PROMPT_INVALID", "纪要 Prompt 版本未正确发布")
        return prompt

    async def _summary_model_config(
        self, session: AsyncSession, *, scope: WorkflowScope
    ) -> ModelConfig:
        config_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{scope.company_id}:visit-summary:{self._settings.llm_provider}",
        )
        await session.execute(
            pg_insert(ModelConfig)
            .values(
                id=config_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                purpose="visit_summary",
                provider=self._settings.llm_provider,
                model_name=self._settings.llm_model,
                secret_ref=_LLM_SECRET_REFERENCE,
                timeout_ms=round(self._settings.llm_timeout_seconds * 1_000),
                max_retries=self._settings.llm_max_retries,
                max_concurrency=self._settings.llm_max_concurrency,
                daily_budget_cny=self._settings.model_daily_budget_cny,
                data_retention="no_training",
                enabled=True,
                parameters={
                    "thinking": self._settings.llm_thinking,
                    "reasoning_effort": self._settings.llm_reasoning_effort,
                    "max_output_tokens": min(self._settings.llm_max_output_tokens, 1_000),
                },
            )
            .on_conflict_do_nothing(constraint="uq_model_configs_purpose_provider")
        )
        config = await session.scalar(
            select(ModelConfig).where(
                ModelConfig.tenant_id == scope.tenant_id,
                ModelConfig.company_id == scope.company_id,
                ModelConfig.purpose == "visit_summary",
                ModelConfig.provider == self._settings.llm_provider,
                ModelConfig.enabled.is_(True),
            )
        )
        if config is None:
            raise ApiError(503, "SUMMARY_MODEL_INVALID", "纪要模型配置不可用")
        if config.model_name != self._settings.llm_model:
            raise ApiError(503, "SUMMARY_MODEL_VERSION_MISMATCH", "纪要模型版本未同步")
        return config

    async def _gap(
        self,
        session: AsyncSession,
        *,
        scope: WorkflowScope,
        gap_id: uuid.UUID,
        for_update: bool = False,
    ) -> KnowledgeGap:
        statement = (
            select(KnowledgeGap)
            .join(Conversation, Conversation.id == KnowledgeGap.conversation_id)
            .join(Card, Card.id == Conversation.card_id)
            .where(
                KnowledgeGap.id == gap_id,
                KnowledgeGap.tenant_id == scope.tenant_id,
                KnowledgeGap.company_id == scope.company_id,
                *self._card_filters(scope),
            )
        )
        if for_update:
            statement = statement.with_for_update(of=KnowledgeGap)
        gap = await session.scalar(statement)
        if gap is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "知识缺口不存在或不在当前作用域")
        return gap

    async def _set_scope(self, session: AsyncSession, scope: WorkflowScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    @staticmethod
    def _card_filters(scope: WorkflowScope) -> tuple[object, ...]:
        if scope.is_card_owner:
            return (Card.owner_user_id == scope.actor_user_id,)
        return ()

    @staticmethod
    def _conversation_item(
        conversation: Conversation,
        display_name: str,
        message_count: int,
        has_summary: bool,
    ) -> ConversationItem:
        return ConversationItem(
            id=conversation.id,
            card_id=conversation.card_id,
            card_display_name=display_name,
            visitor_id=conversation.visitor_id,
            visit_id=conversation.visit_id,
            status=conversation.status.value,
            primary_intent=conversation.primary_intent,
            risk_level=conversation.risk_level,
            started_at=conversation.started_at,
            last_activity_at=conversation.last_activity_at,
            message_count=int(message_count or 0),
            has_current_summary=bool(has_summary),
        )

    @staticmethod
    def _summary_view(summary: VisitSummary) -> SummaryView:
        return SummaryView(
            id=summary.id,
            conversation_id=summary.conversation_id,
            summary=summary.summary,
            interests=list(summary.interests),
            strength=summary.strength,
            next_step=summary.next_step,
            risk_notes=summary.risk_notes,
            source_message_ids=list(summary.source_message_ids),
            is_current=summary.is_current,
            stale_at=summary.stale_at,
            approved_at=summary.approved_at,
            approved_by=summary.approved_by,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )

    @staticmethod
    def _gap_view(gap: KnowledgeGap) -> KnowledgeGapView:
        return KnowledgeGapView(
            id=gap.id,
            conversation_id=gap.conversation_id,
            question=gap.question,
            reason=gap.reason,
            status=gap.status.value,
            suggested_answer=gap.suggested_answer,
            occurrence_count=gap.occurrence_count,
            last_seen_at=gap.last_seen_at,
            approved_version_id=gap.approved_version_id,
            evidence=gap.evidence,
            created_at=gap.created_at,
            updated_at=gap.updated_at,
        )

    @staticmethod
    def _notification_view(notification: Notification) -> NotificationView:
        return NotificationView(
            id=notification.id,
            notification_type=notification.notification_type,
            title=notification.title,
            body=notification.body,
            resource_type=notification.resource_type,
            resource_id=notification.resource_id,
            read_at=notification.read_at,
            created_at=notification.created_at,
        )


def _opportunity_score(question: str) -> float:
    normalized = question.casefold()
    if any(term in normalized for term in ("报价", "预算", "采购", "price", "budget")):
        return 0.9
    if any(term in normalized for term in ("演示", "demo", "联系")):
        return 0.82
    return 0.72


def _opportunity_reason(question: str) -> str:
    normalized = question.casefold()
    if any(term in normalized for term in ("报价", "预算", "采购", "price", "budget")):
        return "商业决策信号（报价、预算或采购）"
    if any(term in normalized for term in ("演示", "demo", "联系")):
        return "跟进信号（演示或联系）"
    return "合作意向信号"


def _profile_strength(value: str | None) -> float:
    normalized = (value or "").strip().casefold()
    if normalized in {"strong", "high", "高", "强", "强烈"}:
        return 0.9
    if normalized in {"medium", "moderate", "中", "中等"}:
        return 0.65
    return 0.35


__all__ = ["GapDocument", "PreparedSummary", "WorkflowScope", "WorkflowStore"]
