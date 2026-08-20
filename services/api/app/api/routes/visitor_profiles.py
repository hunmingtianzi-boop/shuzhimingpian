from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.commercial_dependencies import require_commercial_feature
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.workflow_schemas import (
    PaginationMeta,
    VisitorProfileEnvelope,
    VisitorProfileListEnvelope,
    VisitorProfileOverviewEnvelope,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.visitor_profile_store import VisitorProfileScope, VisitorProfileStore

router = APIRouter(
    tags=["Visitor Profiles"],
    dependencies=[Depends(require_commercial_feature("customer.profiles"))],
)
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _scope(principal: StaffPrincipal) -> VisitorProfileScope:
    return VisitorProfileScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def _authorize(principal: StaffPrincipal) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if role in {"company_admin", "platform_admin", "card_owner"}:
        return
    granted = {str(value) for value in principal.permissions}
    if granted.intersection({"visits.read", "conversations.read", "*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有查看访客画像的权限")


def _store(request: Request) -> VisitorProfileStore:
    return VisitorProfileStore(request.app.state.session_factory, request.app.state.settings)


@router.get(
    "/admin/visitor-profiles",
    response_model=VisitorProfileListEnvelope,
    operation_id="listAdminVisitorProfiles",
)
async def list_visitor_profiles(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> VisitorProfileListEnvelope:
    _authorize(principal)
    items, total = await _store(request).list(
        scope=_scope(principal), limit=limit, offset=offset
    )
    return VisitorProfileListEnvelope(
        data=items,
        meta=PaginationMeta(total=total, limit=limit, offset=offset),
    )


@router.get(
    "/admin/visitor-profiles/{visitor_id}",
    response_model=VisitorProfileEnvelope,
    operation_id="getAdminVisitorProfile",
)
async def get_visitor_profile(
    visitor_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> VisitorProfileEnvelope:
    _authorize(principal)
    return VisitorProfileEnvelope(
        data=await _store(request).get(scope=_scope(principal), visitor_id=visitor_id)
    )


@router.get(
    "/admin/visitor-profiles/{visitor_id}/overview",
    response_model=VisitorProfileOverviewEnvelope,
    operation_id="getAdminVisitorProfileOverview",
)
async def get_visitor_profile_overview(
    visitor_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> VisitorProfileOverviewEnvelope:
    _authorize(principal)
    return VisitorProfileOverviewEnvelope(
        data=await _store(request).overview(
            scope=_scope(principal),
            visitor_id=visitor_id,
            trace_id=request_id_ctx.get(),
        )
    )
