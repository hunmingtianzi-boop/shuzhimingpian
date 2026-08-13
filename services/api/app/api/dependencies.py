from __future__ import annotations

from typing import Annotated

from fastapi import Header, Request

from app.api.errors import ApiError
from app.core.tokens import (
    StaffPrincipal,
    StaffTokenError,
    VisitorPrincipal,
    VisitorTokenError,
    decode_staff_access_token,
    decode_visitor_token,
)
from app.services.auth_store import AuthStore


def get_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key or not (8 <= len(idempotency_key) <= 128):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "请求缺少有效的幂等标识",
            details={"field": "Idempotency-Key"},
        )
    return idempotency_key


def get_visitor_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> VisitorPrincipal:
    settings = request.app.state.settings
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "AUTH_REQUIRED", "访客会话已失效，请刷新页面后重试")
    try:
        return decode_visitor_token(
            token,
            signing_key=settings.jwt_signing_key.get_secret_value(),
            issuer=settings.app_name,
        )
    except VisitorTokenError as exc:
        raise ApiError(401, "TOKEN_EXPIRED", "访客会话已失效，请刷新页面后重试") from exc


async def get_staff_principal(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> StaffPrincipal:
    settings = request.app.state.settings
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "AUTH_REQUIRED", "员工登录状态无效，请重新登录")
    try:
        principal = decode_staff_access_token(
            token,
            signing_key=settings.jwt_signing_key.get_secret_value(),
            issuer=settings.app_name,
        )
    except StaffTokenError as exc:
        raise ApiError(401, "AUTH_REQUIRED", "员工登录状态无效，请重新登录") from exc
    password_change_paths = {
        f"{settings.api_prefix}/auth/me",
        f"{settings.api_prefix}/auth/password",
        f"{settings.api_prefix}/auth/logout",
    }
    if (
        "auth.password.change" in principal.permissions
        and request.url.path not in password_change_paths
    ):
        raise ApiError(403, "PASSWORD_CHANGE_REQUIRED", "首次登录需要先修改临时密码")
    if getattr(request.app.state, "require_staff_session_validation", False):
        identity = await AuthStore(
            request.app.state.session_factory,
            settings,
        ).get_current(principal)
        return StaffPrincipal(
            user_id=identity.user_id,
            membership_id=identity.membership_id,
            tenant_id=identity.tenant_id,
            company_id=identity.company_id,
            role=identity.role,
            permissions=identity.permissions,
            session_id=principal.session_id,
            token_id=principal.token_id,
        )
    return principal
