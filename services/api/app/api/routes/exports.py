from __future__ import annotations

import uuid
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from app.api.commercial_dependencies import require_commercial_feature
from app.api.dependencies import get_idempotency_key, get_staff_principal
from app.api.errors import ApiError
from app.api.export_schemas import (
    CreateExportRequest,
    ExportAvailabilityEnvelope,
    ExportRequestEnvelope,
    ExportRequestListEnvelope,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.export_store import ExportScope, ExportStore, ExportType

router = APIRouter(
    prefix="/admin",
    tags=["Data Exports"],
    dependencies=[Depends(require_commercial_feature("data.exports"))],
)
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
IdempotencyDependency = Annotated[str, Depends(get_idempotency_key)]
_ADMIN_ROLES = {"company_admin", "platform_admin"}
_READ_PERMISSION: dict[ExportType, str] = {
    "visitors": "visits.read",
    "leads": "leads.read",
    "conversations": "conversations.read",
}


def _store(request: Request) -> ExportStore:
    return ExportStore(request.app.state.session_factory, request.app.state.settings)


def _scope(principal: StaffPrincipal) -> ExportScope:
    return ExportScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def _require_export_access(
    principal: StaffPrincipal,
    export_type: ExportType,
    *,
    include_sensitive: bool = False,
) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if include_sensitive and role not in _ADMIN_ROLES:
        raise ApiError(
            403,
            "EXPORT_SENSITIVE_FORBIDDEN",
            "Only company administrators can export unmasked personal data.",
        )
    if role in _ADMIN_ROLES or role == "card_owner":
        return
    granted = {str(value) for value in principal.permissions}
    if _READ_PERMISSION[export_type] in granted or granted.intersection({"*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "The account cannot export this data set.")


def _require_any_export_access(principal: StaffPrincipal) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if role in _ADMIN_ROLES or role == "card_owner":
        return
    granted = {str(value) for value in principal.permissions}
    if granted.intersection({*_READ_PERMISSION.values(), "*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "The account cannot access data exports.")


@router.post(
    "/exports/{export_type}",
    response_model=ExportRequestEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createAdminDataExport",
)
async def create_export(
    export_type: Annotated[
        Literal["visitors", "leads", "conversations"], Path()
    ],
    body: CreateExportRequest,
    request: Request,
    principal: StaffDependency,
    idempotency_key: IdempotencyDependency,
) -> ExportRequestEnvelope:
    _require_export_access(principal, export_type, include_sensitive=body.include_sensitive)
    record = await _store(request).create(
        scope=_scope(principal),
        export_type=export_type,
        include_sensitive=body.include_sensitive,
        idempotency_key=idempotency_key,
        trace_id=request_id_ctx.get(),
    )
    return ExportRequestEnvelope(data=record)


@router.post(
    "/leads:export",
    response_model=ExportRequestEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createAdminLeadExport",
)
async def create_lead_export(
    body: CreateExportRequest,
    request: Request,
    principal: StaffDependency,
    idempotency_key: IdempotencyDependency,
) -> ExportRequestEnvelope:
    _require_export_access(principal, "leads", include_sensitive=body.include_sensitive)
    record = await _store(request).create(
        scope=_scope(principal),
        export_type="leads",
        include_sensitive=body.include_sensitive,
        idempotency_key=idempotency_key,
        trace_id=request_id_ctx.get(),
    )
    return ExportRequestEnvelope(data=record)


@router.get(
    "/exports",
    response_model=ExportRequestListEnvelope,
    operation_id="listAdminDataExports",
)
async def list_exports(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExportRequestListEnvelope:
    _require_any_export_access(principal)
    records, total = await _store(request).list(
        scope=_scope(principal), limit=limit, offset=offset
    )
    return ExportRequestListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/exports/availability",
    response_model=ExportAvailabilityEnvelope,
    operation_id="getAdminDataExportAvailability",
)
async def get_export_availability(
    request: Request,
    principal: StaffDependency,
) -> ExportAvailabilityEnvelope:
    _require_any_export_access(principal)
    availability = await _store(request).availability(scope=_scope(principal))
    return ExportAvailabilityEnvelope(data=availability)


@router.get(
    "/exports/{export_id}",
    response_model=ExportRequestEnvelope,
    operation_id="getAdminDataExport",
)
async def get_export(
    export_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> ExportRequestEnvelope:
    record = await _store(request).get(scope=_scope(principal), export_id=export_id)
    _require_export_access(
        principal,
        record.export_type,
        include_sensitive=record.include_sensitive,
    )
    return ExportRequestEnvelope(data=record)


@router.get(
    "/exports/{export_id}/download",
    operation_id="downloadAdminDataExport",
)
async def download_export(
    export_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> Response:
    record = await _store(request).get(scope=_scope(principal), export_id=export_id)
    _require_export_access(
        principal,
        record.export_type,
        include_sensitive=record.include_sensitive,
    )
    download = await _store(request).download(
        scope=_scope(principal),
        export_id=export_id,
        trace_id=request_id_ctx.get(),
    )
    encoded_name = quote(download.file_name, safe="")
    return Response(
        content=download.content,
        media_type=download.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["router"]
