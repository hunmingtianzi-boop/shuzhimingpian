from __future__ import annotations

import uuid
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, Query, Request, status

from app.api.admin_schemas import CreateKnowledgeDocumentRequest, PutKnowledgeDocumentRequest
from app.api.dependencies import get_staff_principal, get_visitor_principal
from app.api.errors import ApiError
from app.api.workflow_schemas import (
    ConversationDetailEnvelope,
    ConversationListEnvelope,
    DashboardEnvelope,
    EmployeeAnalyticsListEnvelope,
    KnowledgeGapEnvelope,
    KnowledgeGapListEnvelope,
    NotificationEnvelope,
    NotificationListEnvelope,
    OpportunityCandidateListEnvelope,
    SummaryEnvelope,
    TopicAnalysisEnvelope,
    UpdateKnowledgeGapRequest,
    VisitEventEnvelope,
    VisitEventRequest,
    VisitListEnvelope,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal, VisitorPrincipal
from app.services.admin_store import AdminScope, AdminStore
from app.services.summary_provider import DeepSeekSummaryProvider
from app.services.topic_analysis import TopicAnalysisService
from app.services.workflow_store import WorkflowScope, WorkflowStore

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Business Workflow"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
VisitorDependency = Annotated[VisitorPrincipal, Depends(get_visitor_principal)]

_ADMIN_ROLES = {"company_admin", "platform_admin"}


def _scope(principal: StaffPrincipal) -> WorkflowScope:
    return WorkflowScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def _admin_scope(principal: StaffPrincipal) -> AdminScope:
    return AdminScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
    )


def _store(request: Request) -> WorkflowStore:
    return WorkflowStore(
        request.app.state.session_factory,
        request.app.state.settings,
        summary_provider=DeepSeekSummaryProvider(
            request.app.state.settings,
            request.app.state.http_client,
        ),
    )


def _admin_store(request: Request) -> AdminStore:
    return AdminStore.from_runtime(
        session_factory=request.app.state.session_factory,
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
    )


def _topic_service(request: Request) -> TopicAnalysisService:
    return TopicAnalysisService(
        request.app.state.session_factory,
        request.app.state.settings,
        request.app.state.http_client,
        getattr(request.app.state, "redis", None),
        semaphore=getattr(request.app.state, "ai_semaphore", None),
    )


def _require_access(
    principal: StaffPrincipal,
    *permissions: str,
    allow_card_owner: bool = False,
) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if role in _ADMIN_ROLES or (allow_card_owner and role == "card_owner"):
        return
    granted = {str(value) for value in principal.permissions}
    if granted.intersection(permissions) or granted.intersection({"*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有执行此操作的权限")


@router.get(
    "/admin/dashboard",
    response_model=DashboardEnvelope,
    operation_id="getAdminDashboard",
)
async def get_dashboard(
    request: Request,
    principal: StaffDependency,
    period_days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> DashboardEnvelope:
    _require_access(
        principal,
        "analytics.read",
        "visits.read",
        "conversations.read",
        allow_card_owner=True,
    )
    overview = await _store(request).dashboard(scope=_scope(principal), period_days=period_days)
    return DashboardEnvelope(data=overview)


@router.get(
    "/admin/analytics/topics",
    response_model=TopicAnalysisEnvelope,
    operation_id="getAdminTopicAnalysis",
)
async def get_topic_analysis(
    request: Request,
    principal: StaffDependency,
    period_days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> TopicAnalysisEnvelope:
    _require_access(
        principal,
        "analytics.read",
        "conversations.read",
        allow_card_owner=True,
    )
    result = await _topic_service(request).get(
        scope=_scope(principal),
        period_days=period_days,
    )
    return TopicAnalysisEnvelope(data=result)


@router.post(
    "/admin/analytics/topics:analyze",
    response_model=TopicAnalysisEnvelope,
    operation_id="analyzeAdminConversationTopics",
)
async def analyze_topics(
    request: Request,
    principal: StaffDependency,
    period_days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> TopicAnalysisEnvelope:
    _require_access(
        principal,
        "analytics.read",
        "conversations.read",
        allow_card_owner=True,
    )
    result = await _topic_service(request).analyze(
        scope=_scope(principal),
        period_days=period_days,
        trace_id=request_id_ctx.get(),
    )
    return TopicAnalysisEnvelope(data=result)


@router.get(
    "/admin/analytics/employees",
    response_model=EmployeeAnalyticsListEnvelope,
    operation_id="listEmployeeAnalytics",
)
async def list_employee_analytics(
    request: Request,
    principal: StaffDependency,
    period_days: Annotated[int, Query(ge=1, le=90)] = 30,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort_by: Literal[
        "display_name",
        "card_count",
        "visits",
        "unique_visitors",
        "conversations",
        "leads",
        "conversation_rate",
        "lead_rate",
        "last_activity_at",
    ] = "visits",
    sort_order: Literal["asc", "desc"] = "desc",
) -> EmployeeAnalyticsListEnvelope:
    _require_access(principal, "analytics.read", allow_card_owner=True)
    records, reconciliation, total, generated_at = await _store(
        request
    ).list_employee_analytics(
        scope=_scope(principal),
        period_days=period_days,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return EmployeeAnalyticsListEnvelope(
        data=records,
        reconciliation=reconciliation,
        generated_at=generated_at,
        period_days=period_days,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/admin/visits",
    response_model=VisitListEnvelope,
    operation_id="listAdminVisits",
)
async def list_visits(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    card_id: uuid.UUID | None = None,
) -> VisitListEnvelope:
    _require_access(principal, "visits.read", "conversations.read", allow_card_owner=True)
    records, total = await _store(request).list_visits(
        scope=_scope(principal),
        limit=limit,
        offset=offset,
        card_id=card_id,
    )
    return VisitListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/admin/conversations",
    response_model=ConversationListEnvelope,
    operation_id="listAdminConversations",
)
async def list_conversations(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    conversation_status: Annotated[
        str | None,
        Query(alias="status", pattern=r"^(active|closed|expired|blocked)$"),
    ] = None,
    card_id: uuid.UUID | None = None,
    visitor_id: uuid.UUID | None = None,
) -> ConversationListEnvelope:
    _require_access(principal, "conversations.read", allow_card_owner=True)
    records, total = await _store(request).list_conversations(
        scope=_scope(principal),
        limit=limit,
        offset=offset,
        status=conversation_status,
        card_id=card_id,
        visitor_id=visitor_id,
    )
    return ConversationListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/admin/opportunities",
    response_model=OpportunityCandidateListEnvelope,
    operation_id="listAdminOpportunities",
)
async def list_opportunities(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OpportunityCandidateListEnvelope:
    _require_access(principal, "conversations.read", allow_card_owner=True)
    records, total = await _store(request).list_opportunities(
        scope=_scope(principal), limit=limit, offset=offset
    )
    return OpportunityCandidateListEnvelope(
        data=records, total=total, limit=limit, offset=offset
    )


@router.get(
    "/admin/conversations/{conversation_id}",
    response_model=ConversationDetailEnvelope,
    operation_id="getAdminConversation",
)
async def get_conversation(
    conversation_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> ConversationDetailEnvelope:
    _require_access(principal, "conversations.read", allow_card_owner=True)
    detail = await _store(request).get_conversation(
        scope=_scope(principal),
        conversation_id=conversation_id,
        trace_id=request_id_ctx.get(),
    )
    return ConversationDetailEnvelope(data=detail)


@router.post(
    "/admin/conversations/{conversation_id}/summary:generate",
    response_model=SummaryEnvelope,
    operation_id="generateConversationSummary",
)
@router.post(
    "/admin/conversations/{conversation_id}:summarize",
    response_model=SummaryEnvelope,
    operation_id="summarizeConversation",
)
async def generate_summary(
    conversation_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> SummaryEnvelope:
    _require_access(
        principal,
        "summaries.write",
        "conversations.write",
        allow_card_owner=True,
    )
    summary = await _store(request).generate_summary(
        scope=_scope(principal),
        conversation_id=conversation_id,
        trace_id=request_id_ctx.get(),
    )
    return SummaryEnvelope(data=summary)


@router.get(
    "/admin/summaries/{summary_id}",
    response_model=SummaryEnvelope,
    operation_id="getVisitSummary",
)
async def get_summary(
    summary_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> SummaryEnvelope:
    _require_access(principal, "summaries.read", "conversations.read", allow_card_owner=True)
    summary = await _store(request).get_summary(
        scope=_scope(principal),
        summary_id=summary_id,
        trace_id=request_id_ctx.get(),
    )
    return SummaryEnvelope(data=summary)


@router.post(
    "/admin/summaries/{summary_id}:approve",
    response_model=SummaryEnvelope,
    operation_id="approveVisitSummary",
)
async def approve_summary(
    summary_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> SummaryEnvelope:
    _require_access(
        principal, "summaries.write", "conversations.write", allow_card_owner=True
    )
    return SummaryEnvelope(
        data=await _store(request).approve_summary(
            scope=_scope(principal),
            summary_id=summary_id,
            trace_id=request_id_ctx.get(),
        )
    )


@router.get(
    "/admin/knowledge/gaps",
    response_model=KnowledgeGapListEnvelope,
    operation_id="listKnowledgeGaps",
)
async def list_knowledge_gaps(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    gap_status: Annotated[
        str | None,
        Query(
            alias="status",
            pattern=r"^(pending|drafted|approved|indexing|indexed|rejected|failed)$",
        ),
    ] = None,
) -> KnowledgeGapListEnvelope:
    _require_access(principal, "knowledge.read", "knowledge.review", allow_card_owner=True)
    records, total = await _store(request).list_gaps(
        scope=_scope(principal),
        limit=limit,
        offset=offset,
        status=gap_status,
    )
    return KnowledgeGapListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.patch(
    "/admin/knowledge/gaps/{gap_id}",
    response_model=KnowledgeGapEnvelope,
    operation_id="updateKnowledgeGapDraft",
)
async def update_knowledge_gap(
    gap_id: uuid.UUID,
    body: UpdateKnowledgeGapRequest,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeGapEnvelope:
    _require_access(principal, "knowledge.review", "knowledge.write")
    gap = await _store(request).update_gap_answer(
        scope=_scope(principal),
        gap_id=gap_id,
        suggested_answer=body.suggested_answer,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeGapEnvelope(data=gap)


@router.post(
    "/admin/knowledge/gaps/{gap_id}/approve",
    response_model=KnowledgeGapEnvelope,
    operation_id="approveKnowledgeGap",
)
@router.post(
    "/admin/knowledge/gaps/{gap_id}:approve",
    response_model=KnowledgeGapEnvelope,
    operation_id="approveKnowledgeGapContract",
)
async def approve_knowledge_gap(
    gap_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeGapEnvelope:
    _require_access(principal, "knowledge.publish", "knowledge.review")
    workflow = _store(request)
    scope = _scope(principal)
    gap = await workflow.get_gap(scope=scope, gap_id=gap_id)
    if gap.status == "indexed" and gap.approved_version_id:
        return KnowledgeGapEnvelope(data=gap)
    if not gap.suggested_answer:
        raise ApiError(409, "GAP_ANSWER_REQUIRED", "请先补充建议答案")
    await workflow.begin_gap_publish(
        scope=scope,
        gap_id=gap_id,
        trace_id=request_id_ctx.get(),
    )
    try:
        document = await workflow.find_gap_document(scope=scope, gap_id=gap_id)
        if document is not None and document.status.value == "published":
            if document.current_version_id is None:
                raise ApiError(409, "KNOWLEDGE_STATE_INVALID", "已发布知识缺少当前版本")
            indexed = await workflow.mark_gap_indexed(
                scope=scope,
                gap_id=gap_id,
                version_id=document.current_version_id,
                trace_id=request_id_ctx.get(),
            )
            return KnowledgeGapEnvelope(data=indexed)

        admin = _admin_store(request)
        if document is None:
            created = await admin.create_document(
                scope=_admin_scope(principal),
                body=CreateKnowledgeDocumentRequest(
                    title=gap.question[:500],
                    source_type="knowledge_gap",
                    source_id=str(gap.id),
                ),
                trace_id=request_id_ctx.get(),
            )
            document_id = created.id
        else:
            document_id = document.id
        draft = await admin.put_document_draft(
            scope=_admin_scope(principal),
            document_id=document_id,
            body=PutKnowledgeDocumentRequest(
                raw_text=f"问题：{gap.question}\n\n回答：{gap.suggested_answer}",
                title=gap.question[:500],
                visibility="public",
                metadata={
                    "source_label": "企业审核通过的知识补充",
                    "knowledge_gap_id": str(gap.id),
                },
            ),
            trace_id=request_id_ctx.get(),
        )
        published = await admin.publish_document(
            scope=_admin_scope(principal),
            document_id=document_id,
            version_id=draft.draft_version.id,
            trace_id=request_id_ctx.get(),
        )
        indexed = await workflow.mark_gap_indexed(
            scope=scope,
            gap_id=gap_id,
            version_id=published.published_version.id,
            trace_id=request_id_ctx.get(),
        )
        return KnowledgeGapEnvelope(data=indexed)
    except Exception as exc:
        try:
            await workflow.mark_gap_failed(
                scope=scope,
                gap_id=gap_id,
                error_code=getattr(exc, "code", type(exc).__name__),
                trace_id=request_id_ctx.get(),
            )
        except Exception as mark_error:
            logger.error(
                "knowledge_gap_failure_state_update_failed",
                gap_id=str(gap_id),
                error_type=type(mark_error).__name__,
            )
        raise


@router.post(
    "/admin/knowledge/gaps/{gap_id}/reject",
    response_model=KnowledgeGapEnvelope,
    operation_id="rejectKnowledgeGap",
)
@router.post(
    "/admin/knowledge/gaps/{gap_id}:reject",
    response_model=KnowledgeGapEnvelope,
    operation_id="rejectKnowledgeGapContract",
)
async def reject_knowledge_gap(
    gap_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeGapEnvelope:
    _require_access(principal, "knowledge.review")
    gap = await _store(request).reject_gap(
        scope=_scope(principal),
        gap_id=gap_id,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeGapEnvelope(data=gap)


@router.get(
    "/admin/notifications",
    response_model=NotificationListEnvelope,
    operation_id="listNotifications",
)
async def list_notifications(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    unread_only: bool = False,
) -> NotificationListEnvelope:
    records, total, unread = await _store(request).list_notifications(
        scope=_scope(principal),
        limit=limit,
        unread_only=unread_only,
    )
    return NotificationListEnvelope(data=records, total=total, unread=unread)


@router.post(
    "/admin/notifications/{notification_id}/read",
    response_model=NotificationEnvelope,
    operation_id="markNotificationRead",
)
async def mark_notification_read(
    notification_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> NotificationEnvelope:
    notification = await _store(request).mark_notification_read(
        scope=_scope(principal),
        notification_id=notification_id,
    )
    return NotificationEnvelope(data=notification)


@router.post(
    "/public/cards/{slug}/visits/{visit_id}/events",
    response_model=VisitEventEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="recordVisitEvent",
)
async def record_visit_event(
    slug: str,
    visit_id: uuid.UUID,
    body: VisitEventRequest,
    request: Request,
    principal: VisitorDependency,
) -> VisitEventEnvelope:
    if principal.visit_id != visit_id:
        raise ApiError(403, "VISITOR_SCOPE_MISMATCH", "访问会话令牌与路径不匹配")
    event = await _store(request).record_visit_event(
        slug=slug,
        principal_tenant_id=principal.tenant_id,
        principal_company_id=principal.company_id,
        principal_card_id=principal.card_id,
        principal_visitor_id=principal.visitor_id,
        principal_visit_id=principal.visit_id,
        request=body,
    )
    return VisitEventEnvelope(data=event)


__all__ = ["router"]
