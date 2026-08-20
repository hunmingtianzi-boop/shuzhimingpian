from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.commercial_dependencies import commercial_actor
from app.api.commercial_schemas import (
    CommercialEntitlementEnvelope,
    UpdateCommercialEntitlementRequest,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.platform_schemas import (
    CreateEnterpriseRequest,
    EnterpriseEnvelope,
    EnterpriseListEnvelope,
    PlatformEnterpriseLifecycleEnvelope,
    TransitionPlatformEnterpriseRequest,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.commercial_store import CommercialStore
from app.services.platform_store import PlatformActor, PlatformStore

router = APIRouter(prefix="/platform/enterprises", tags=["Platform Administration"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _store(request: Request) -> PlatformStore:
    return PlatformStore(
        request.app.state.session_factory,
        request.app.state.settings,
        public_card_base_url=getattr(request.app.state, "public_card_base_url", None),
    )


def _actor(principal: StaffPrincipal) -> PlatformActor:
    return PlatformActor(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        session_id=principal.session_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


@router.post(
    "",
    response_model=EnterpriseEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPlatformEnterprise",
)
async def create_enterprise(
    body: CreateEnterpriseRequest,
    request: Request,
    principal: StaffDependency,
) -> EnterpriseEnvelope:
    record = await _store(request).create_enterprise(
        actor=_actor(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return EnterpriseEnvelope(data=record)


@router.get(
    "",
    response_model=EnterpriseListEnvelope,
    operation_id="listPlatformEnterprises",
)
async def list_enterprises(
    request: Request,
    principal: StaffDependency,
    search: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[
        str | None,
        Query(alias="status", pattern="^(active|suspended|disabled)$"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EnterpriseListEnvelope:
    if str(getattr(principal.role, "value", principal.role)) != "platform_admin":
        raise ApiError(403, "FORBIDDEN", "仅平台管理员可查看企业清单")
    records, total = await _store(request).list_enterprises(
        actor=_actor(principal),
        search=search.strip() if search and search.strip() else None,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return EnterpriseListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.put(
    "/{company_id}/status",
    response_model=PlatformEnterpriseLifecycleEnvelope,
    operation_id="transitionPlatformEnterprise",
)
async def transition_enterprise(
    company_id: uuid.UUID,
    body: TransitionPlatformEnterpriseRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformEnterpriseLifecycleEnvelope:
    if str(getattr(principal.role, "value", principal.role)) != "platform_admin":
        raise ApiError(403, "FORBIDDEN", "仅平台管理员可变更企业状态")
    record = await _store(request).transition_enterprise(
        actor=_actor(principal),
        company_id=company_id,
        expected_version=body.expected_version,
        target_status=body.target_status,
        reason=body.reason,
        trace_id=request_id_ctx.get(),
    )
    return PlatformEnterpriseLifecycleEnvelope(data=record)


@router.get(
    "/{company_id}/entitlements",
    response_model=CommercialEntitlementEnvelope,
    operation_id="getPlatformEnterpriseEntitlements",
)
async def get_enterprise_entitlements(
    company_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> CommercialEntitlementEnvelope:
    record = await CommercialStore(request.app.state.session_factory).get_entitlements(
        actor=commercial_actor(principal),
        company_id=company_id,
    )
    return CommercialEntitlementEnvelope(data=record)


@router.put(
    "/{company_id}/entitlements",
    response_model=CommercialEntitlementEnvelope,
    operation_id="updatePlatformEnterpriseEntitlements",
)
async def update_enterprise_entitlements(
    company_id: uuid.UUID,
    body: UpdateCommercialEntitlementRequest,
    request: Request,
    principal: StaffDependency,
) -> CommercialEntitlementEnvelope:
    record = await CommercialStore(request.app.state.session_factory).update_entitlements(
        actor=commercial_actor(principal),
        company_id=company_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return CommercialEntitlementEnvelope(data=record)


__all__ = ["router"]
