from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.commercial_dependencies import require_commercial_feature
from app.api.dependencies import (
    get_idempotency_key,
    get_staff_principal,
    get_visitor_principal,
)
from app.api.errors import ApiError
from app.api.routes.admin import parse_if_match
from app.api.workflow_schemas import (
    CreateLeadFollowupRequest,
    LeadCaptureRequest,
    LeadCreatedEnvelope,
    LeadDetailEnvelope,
    LeadFollowupEnvelope,
    LeadListEnvelope,
    PrivacyRequestCreate,
    PrivacyRequestEnvelope,
    PrivacyRequestListEnvelope,
    UpdateLeadRequest,
    UpdatePrivacyRequest,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal, VisitorPrincipal
from app.services.crm_store import CrmScope, CrmStore

router = APIRouter(tags=["Leads and Privacy"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
VisitorDependency = Annotated[VisitorPrincipal, Depends(get_visitor_principal)]
IdempotencyDependency = Annotated[str, Depends(get_idempotency_key)]
IfMatchDependency = Annotated[str, Header(alias="If-Match")]
_ADMIN_ROLES = {"company_admin", "platform_admin"}


def _store(request: Request) -> CrmStore:
    return CrmStore(request.app.state.session_factory, request.app.state.settings)


def _scope(principal: StaffPrincipal) -> CrmScope:
    return CrmScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        role=str(getattr(principal.role, "value", principal.role)),
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


def _set_etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


@router.post(
    "/public/cards/{slug}/leads",
    response_model=LeadCreatedEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPublicLead",
)
async def create_public_lead(
    slug: str,
    body: LeadCaptureRequest,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> LeadCreatedEnvelope:
    lead = await _store(request).create_public_lead(
        slug=slug,
        principal=principal,
        body=body,
        idempotency_key=idempotency_key,
    )
    return LeadCreatedEnvelope(data=lead)


@router.post(
    "/public/privacy-requests",
    response_model=PrivacyRequestEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPrivacyRequest",
)
async def create_privacy_request(
    body: PrivacyRequestCreate,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> PrivacyRequestEnvelope:
    record = await _store(request).create_privacy_request(
        principal=principal,
        body=body,
        idempotency_key=idempotency_key,
    )
    return PrivacyRequestEnvelope(data=record)


@router.get(
    "/public/privacy-requests/{privacy_request_id}",
    response_model=PrivacyRequestEnvelope,
    operation_id="getPrivacyRequest",
)
async def get_privacy_request(
    privacy_request_id: uuid.UUID,
    request: Request,
    principal: VisitorDependency,
) -> PrivacyRequestEnvelope:
    record = await _store(request).get_public_privacy_request(
        principal=principal,
        request_id=privacy_request_id,
    )
    return PrivacyRequestEnvelope(data=record)


@router.get(
    "/admin/leads",
    response_model=LeadListEnvelope,
    operation_id="listAdminLeads",
    dependencies=[Depends(require_commercial_feature("customer.leads"))],
)
async def list_leads(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    lead_status: Annotated[
        str | None,
        Query(alias="status", pattern=r"^(new|viewed|following|won|lost|invalid)$"),
    ] = None,
) -> LeadListEnvelope:
    _require_access(principal, "leads.read", allow_card_owner=True)
    records, total = await _store(request).list_leads(
        scope=_scope(principal),
        limit=limit,
        offset=offset,
        status=lead_status,
    )
    return LeadListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/admin/leads/{lead_id}",
    response_model=LeadDetailEnvelope,
    operation_id="getAdminLead",
    dependencies=[Depends(require_commercial_feature("customer.leads"))],
)
async def get_lead(
    lead_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> LeadDetailEnvelope:
    _require_access(principal, "leads.read", allow_card_owner=True)
    lead = await _store(request).get_lead(
        scope=_scope(principal),
        lead_id=lead_id,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, lead.version)
    return LeadDetailEnvelope(data=lead)


@router.patch(
    "/admin/leads/{lead_id}",
    response_model=LeadDetailEnvelope,
    operation_id="updateAdminLead",
    dependencies=[Depends(require_commercial_feature("customer.leads"))],
)
async def update_lead(
    lead_id: uuid.UUID,
    body: UpdateLeadRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> LeadDetailEnvelope:
    _require_access(principal, "leads.write", allow_card_owner=True)
    lead = await _store(request).update_lead(
        scope=_scope(principal),
        lead_id=lead_id,
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, lead.version)
    return LeadDetailEnvelope(data=lead)


@router.post(
    "/admin/leads/{lead_id}/followups",
    response_model=LeadFollowupEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createLeadFollowup",
    dependencies=[Depends(require_commercial_feature("customer.leads"))],
)
async def create_followup(
    lead_id: uuid.UUID,
    body: CreateLeadFollowupRequest,
    request: Request,
    principal: StaffDependency,
) -> LeadFollowupEnvelope:
    _require_access(principal, "leads.write", allow_card_owner=True)
    followup = await _store(request).add_followup(
        scope=_scope(principal),
        lead_id=lead_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return LeadFollowupEnvelope(data=followup)


@router.get(
    "/admin/privacy-requests",
    response_model=PrivacyRequestListEnvelope,
    operation_id="listAdminPrivacyRequests",
)
async def list_privacy_requests(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    privacy_status: Annotated[
        str | None,
        Query(alias="status", pattern=r"^(pending|verified|in_progress|completed|rejected)$"),
    ] = None,
) -> PrivacyRequestListEnvelope:
    _require_access(principal, "privacy.manage")
    records, total = await _store(request).list_privacy_requests(
        scope=_scope(principal),
        limit=limit,
        offset=offset,
        status=privacy_status,
    )
    return PrivacyRequestListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.patch(
    "/admin/privacy-requests/{privacy_request_id}",
    response_model=PrivacyRequestEnvelope,
    operation_id="updateAdminPrivacyRequest",
)
async def update_privacy_request(
    privacy_request_id: uuid.UUID,
    body: UpdatePrivacyRequest,
    request: Request,
    principal: StaffDependency,
) -> PrivacyRequestEnvelope:
    _require_access(principal, "privacy.manage")
    record = await _store(request).update_privacy_request(
        scope=_scope(principal),
        request_id=privacy_request_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return PrivacyRequestEnvelope(data=record)


__all__ = ["router"]
