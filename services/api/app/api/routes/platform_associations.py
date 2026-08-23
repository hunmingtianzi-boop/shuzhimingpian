from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.dependencies import get_staff_principal
from app.api.platform_schemas import (
    PlatformAssociationListEnvelope,
    PlatformAssociationMember,
    PlatformAssociationMemberEnvelope,
    PlatformAssociationMemberListEnvelope,
    PlatformAssociationSummary,
    UpsertPlatformAssociationMemberRequest,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.platform_associations import (
    PlatformAssociationActor,
    PlatformAssociationService,
)

router = APIRouter(prefix="/platform/associations", tags=["Platform Associations"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _actor(principal: StaffPrincipal) -> PlatformAssociationActor:
    return PlatformAssociationActor(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        session_id=principal.session_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def _service(request: Request) -> PlatformAssociationService:
    return PlatformAssociationService(request.app.state.session_factory)


@router.get(
    "",
    response_model=PlatformAssociationListEnvelope,
    operation_id="listPlatformAssociations",
)
async def list_associations(
    request: Request,
    principal: StaffDependency,
) -> PlatformAssociationListEnvelope:
    rows = await _service(request).list_associations(actor=_actor(principal))
    return PlatformAssociationListEnvelope(
        data=[PlatformAssociationSummary(**asdict(row)) for row in rows]
    )


@router.get(
    "/{association_company_id}/members",
    response_model=PlatformAssociationMemberListEnvelope,
    operation_id="listPlatformAssociationMembers",
)
async def list_association_members(
    association_company_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> PlatformAssociationMemberListEnvelope:
    rows = await _service(request).list_members(
        actor=_actor(principal), association_company_id=association_company_id
    )
    return PlatformAssociationMemberListEnvelope(
        data=[PlatformAssociationMember(**asdict(row)) for row in rows]
    )


@router.put(
    "/{association_company_id}/members/{member_company_id}",
    response_model=PlatformAssociationMemberEnvelope,
    operation_id="upsertPlatformAssociationMember",
)
async def upsert_association_member(
    association_company_id: uuid.UUID,
    member_company_id: uuid.UUID,
    body: UpsertPlatformAssociationMemberRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformAssociationMemberEnvelope:
    row = await _service(request).upsert_member(
        actor=_actor(principal),
        association_company_id=association_company_id,
        member_company_id=member_company_id,
        expected_version=body.expected_version,
        member_tier=body.member_tier,
        allocated_seats=body.allocated_seats,
        benefits=body.benefits,
        trace_id=request_id_ctx.get(),
    )
    return PlatformAssociationMemberEnvelope(data=PlatformAssociationMember(**asdict(row)))


@router.delete(
    "/{association_company_id}/members/{member_company_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="removePlatformAssociationMember",
)
async def remove_association_member(
    association_company_id: uuid.UUID,
    member_company_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    expected_version: int = Query(ge=1),
) -> Response:
    await _service(request).remove_member(
        actor=_actor(principal),
        association_company_id=association_company_id,
        member_company_id=member_company_id,
        expected_version=expected_version,
        trace_id=request_id_ctx.get(),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
