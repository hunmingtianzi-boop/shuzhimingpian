from __future__ import annotations

import csv
import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.member_schemas import (
    BulkMemberCsvRequest,
    BulkMemberEnvelope,
    BulkMemberRequest,
    CreateMemberRequest,
    MemberEnvelope,
    MemberListEnvelope,
    PasswordResetEnvelope,
    ResetMemberPasswordRequest,
    UpdateMemberAccessRequest,
    UpdateMemberStatusRequest,
    UpdateSelfProfileRequest,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.member_store import MemberScope, MemberStore

router = APIRouter(prefix="/admin/members", tags=["Admin Members"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]

_ADMIN_ROLES = {"company_admin", "platform_admin"}
_MEMBER_PERMISSIONS = {"members.manage", "members.write", "company.manage", "admin:*", "*"}
_CSV_COLUMNS = {
    "account",
    "display_name",
    "password",
    "email",
    "mobile",
    "job_title",
    "avatar_url",
    "business_summary",
    "role",
    "permissions",
    "status",
    "rotate_password",
}


def _store(request: Request) -> MemberStore:
    override = getattr(request.app.state, "member_store", None)
    if override is not None:
        return override
    return MemberStore(request.app.state.session_factory, request.app.state.settings)


def _self_scope(principal: StaffPrincipal) -> MemberScope:
    if principal.company_id is None:
        raise ApiError(
            403,
            "COMPANY_SCOPE_REQUIRED",
            "Select a company scope before updating the member profile.",
        )
    role = str(getattr(principal.role, "value", principal.role))
    granted = {str(value) for value in principal.permissions}
    return MemberScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        actor_session_id=principal.session_id,
        actor_role=role,
        actor_permissions=tuple(sorted(granted)),
    )


def _scope(principal: StaffPrincipal) -> MemberScope:
    scope = _self_scope(principal)
    role = scope.actor_role
    granted = set(scope.actor_permissions)
    if role not in _ADMIN_ROLES and not granted.intersection(_MEMBER_PERMISSIONS):
        raise ApiError(403, "FORBIDDEN", "The current account cannot manage company members.")
    return scope


@router.get("", response_model=MemberListEnvelope, operation_id="listCompanyMembers")
async def list_members(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> MemberListEnvelope:
    records, total = await _store(request).list_members(
        scope=_scope(principal),
        limit=limit,
        offset=offset,
    )
    return MemberListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "",
    response_model=MemberEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCompanyMember",
)
async def create_member(
    body: CreateMemberRequest,
    request: Request,
    principal: StaffDependency,
) -> MemberEnvelope:
    member = await _store(request).create_member(
        scope=_scope(principal),
        row=body,
        trace_id=request_id_ctx.get(),
    )
    return MemberEnvelope(data=member)


@router.patch(
    "/me/profile",
    response_model=MemberEnvelope,
    operation_id="updateCurrentCompanyMemberProfile",
)
async def update_current_member_profile(
    body: UpdateSelfProfileRequest,
    request: Request,
    principal: StaffDependency,
) -> MemberEnvelope:
    member = await _store(request).update_self_profile(
        scope=_self_scope(principal),
        membership_id=principal.membership_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return MemberEnvelope(data=member)


@router.get(
    "/{membership_id}",
    response_model=MemberEnvelope,
    operation_id="getCompanyMember",
)
async def get_member(
    membership_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> MemberEnvelope:
    member = await _store(request).get_member(
        scope=_scope(principal),
        membership_id=membership_id,
    )
    return MemberEnvelope(data=member)


@router.patch(
    "/{membership_id}",
    response_model=MemberEnvelope,
    operation_id="updateCompanyMemberAccess",
)
async def update_member_access(
    membership_id: uuid.UUID,
    body: UpdateMemberAccessRequest,
    request: Request,
    principal: StaffDependency,
) -> MemberEnvelope:
    member = await _store(request).update_access(
        scope=_scope(principal),
        membership_id=membership_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return MemberEnvelope(data=member)


@router.put(
    "/{membership_id}/status",
    response_model=MemberEnvelope,
    operation_id="updateCompanyMemberStatus",
)
async def update_member_status(
    membership_id: uuid.UUID,
    body: UpdateMemberStatusRequest,
    request: Request,
    principal: StaffDependency,
) -> MemberEnvelope:
    member = await _store(request).set_status(
        scope=_scope(principal),
        membership_id=membership_id,
        status=body.status,
        trace_id=request_id_ctx.get(),
    )
    return MemberEnvelope(data=member)


@router.post(
    "/{membership_id}/password:reset",
    response_model=PasswordResetEnvelope,
    operation_id="resetCompanyMemberPassword",
)
async def reset_member_password(
    membership_id: uuid.UUID,
    body: ResetMemberPasswordRequest,
    request: Request,
    principal: StaffDependency,
) -> PasswordResetEnvelope:
    reset = await _store(request).reset_password(
        scope=_scope(principal),
        membership_id=membership_id,
        password=body.password.get_secret_value(),
        revoke_sessions=body.revoke_sessions,
        trace_id=request_id_ctx.get(),
    )
    return PasswordResetEnvelope(data=reset)


@router.post(
    "/bulk",
    response_model=BulkMemberEnvelope,
    operation_id="bulkUpsertCompanyMembers",
)
async def bulk_upsert_members(
    body: BulkMemberRequest,
    request: Request,
    principal: StaffDependency,
) -> BulkMemberEnvelope:
    result = await _store(request).bulk_upsert(
        scope=_scope(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return BulkMemberEnvelope(data=result)


@router.post(
    "/bulk:csv",
    response_model=BulkMemberEnvelope,
    operation_id="bulkUpsertCompanyMembersCsv",
)
async def bulk_upsert_members_csv(
    body: BulkMemberCsvRequest,
    request: Request,
    principal: StaffDependency,
) -> BulkMemberEnvelope:
    rows = _parse_csv(body.csv_text)
    result = await _store(request).bulk_upsert(
        scope=_scope(principal),
        body=BulkMemberRequest(rows=rows),
        trace_id=request_id_ctx.get(),
    )
    return BulkMemberEnvelope(data=result)


def _parse_csv(csv_text: str) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")), strict=True)
        fields = set(reader.fieldnames or ())
        if not {"account", "display_name", "password"}.issubset(fields):
            raise ApiError(
                422,
                "CSV_COLUMNS_INVALID",
                "CSV requires account, display_name, and password columns.",
            )
        unknown = fields - _CSV_COLUMNS
        if unknown:
            raise ApiError(
                422,
                "CSV_COLUMNS_INVALID",
                "CSV contains unsupported columns.",
                details={"fields": sorted(unknown)},
            )
        rows: list[dict[str, Any]] = []
        for raw in reader:
            if len(rows) >= 100:
                raise ApiError(422, "CSV_TOO_MANY_ROWS", "CSV supports at most 100 rows.")
            row = {key: value for key, value in raw.items() if value not in (None, "")}
            permissions = row.get("permissions")
            if isinstance(permissions, str):
                row["permissions"] = [
                    value.strip() for value in permissions.split("|") if value.strip()
                ]
            rotate_password = row.get("rotate_password")
            if isinstance(rotate_password, str):
                normalized = rotate_password.casefold()
                if normalized in {"true", "1", "yes"}:
                    row["rotate_password"] = True
                elif normalized in {"false", "0", "no"}:
                    row["rotate_password"] = False
            rows.append(row)
    except csv.Error as exc:
        raise ApiError(422, "CSV_INVALID", "CSV text cannot be parsed.") from exc
    if not rows:
        raise ApiError(422, "CSV_EMPTY", "CSV contains no member rows.")
    return rows


__all__ = ["router"]
