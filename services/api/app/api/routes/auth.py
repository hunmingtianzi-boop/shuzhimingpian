from __future__ import annotations

import hmac
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response

from app.api.auth_schemas import (
    AuthEnvelope,
    ChangePasswordData,
    ChangePasswordEnvelope,
    ChangePasswordRequest,
    CurrentStaffData,
    CurrentStaffEnvelope,
    LoginRequest,
    LogoutData,
    LogoutEnvelope,
    StaffMembershipView,
    StaffTokenData,
    StaffUserView,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.core.config import Settings
from app.core.rate_limit import RateLimitBackendUnavailable, RedisRateLimiter
from app.core.request_security import account_subject_hash, request_ip_hash
from app.core.tokens import IssuedStaffTokens, StaffPrincipal
from app.services.auth_store import AuthStore, StaffIdentity

router = APIRouter(prefix="/auth", tags=["Auth"])


def _store(request: Request) -> AuthStore:
    return AuthStore(request.app.state.session_factory, request.app.state.settings)


@router.post("/login", response_model=AuthEnvelope, operation_id="login")
async def login(body: LoginRequest, request: Request, response: Response) -> AuthEnvelope:
    """Authenticate staff and set refresh/CSRF cookies without exposing refresh credentials."""

    store = _store(request)
    settings = request.app.state.settings
    account_hash = account_subject_hash(settings, body.account)
    ip_hash = request_ip_hash(request, settings)
    await _enforce_auth_rate_limit(
        request=request,
        store=store,
        event_type="staff.login",
        account_hash=account_hash,
        request_ip_hash_value=ip_hash,
        checks=(
            ("staff-login-ip", ip_hash, settings.staff_login_ip_rate_limit_per_minute),
            (
                "staff-login-account",
                account_hash,
                settings.staff_login_account_rate_limit_per_minute,
            ),
        ),
    )
    authentication = await store.login(
        account=body.account,
        credential=body.credential,
        account_hash=account_hash,
        request_ip_hash=ip_hash,
    )
    return _token_envelope_with_cookies(response, authentication.tokens, settings)


@router.post(
    "/refresh",
    response_model=AuthEnvelope,
    operation_id="refreshStaffSession",
)
async def refresh(
    request: Request,
    response: Response,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthEnvelope:
    """Rotate the HttpOnly refresh cookie after double-submit CSRF validation."""

    store = _store(request)
    settings = request.app.state.settings
    ip_hash = request_ip_hash(request, settings)
    await _enforce_auth_rate_limit(
        request=request,
        store=store,
        event_type="staff.refresh",
        request_ip_hash_value=ip_hash,
        checks=(("staff-refresh-ip", ip_hash, settings.staff_refresh_ip_rate_limit_per_minute),),
    )
    await _enforce_csrf(
        request=request,
        store=store,
        event_type="staff.refresh",
        request_ip_hash_value=ip_hash,
        supplied_token=x_csrf_token,
    )
    refresh_token = request.cookies.get(settings.staff_refresh_cookie_name)
    if not refresh_token or not 32 <= len(refresh_token) <= 4_096:
        await store.record_security_event(
            event_type="staff.refresh",
            outcome="failed",
            request_ip_hash=ip_hash,
            reason_code="refresh_cookie_missing",
        )
        raise ApiError(401, "INVALID_REFRESH_TOKEN", "刷新凭证无效，请重新登录")
    authentication = await store.refresh(refresh_token, request_ip_hash=ip_hash)
    return _token_envelope_with_cookies(response, authentication.tokens, settings)


@router.post(
    "/logout",
    response_model=LogoutEnvelope,
    operation_id="logoutStaffSession",
)
async def logout(
    request: Request,
    response: Response,
    principal: Annotated[StaffPrincipal, Depends(get_staff_principal)],
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> LogoutEnvelope:
    """Revoke the staff session and expire both auth cookies after CSRF validation."""

    store = _store(request)
    settings = request.app.state.settings
    ip_hash = request_ip_hash(request, settings)
    await _enforce_csrf(
        request=request,
        store=store,
        event_type="staff.logout",
        request_ip_hash_value=ip_hash,
        supplied_token=x_csrf_token,
    )
    await store.logout(
        principal,
        request_ip_hash=ip_hash,
    )
    _clear_auth_cookies(response, settings)
    _set_no_store(response)
    return LogoutEnvelope(data=LogoutData())


@router.get(
    "/me",
    response_model=CurrentStaffEnvelope,
    operation_id="getCurrentUser",
)
async def me(
    request: Request,
    principal: Annotated[StaffPrincipal, Depends(get_staff_principal)],
) -> CurrentStaffEnvelope:
    identity = await _store(request).get_current(principal)
    return _current_staff_envelope(identity)


@router.post(
    "/password",
    response_model=ChangePasswordEnvelope,
    operation_id="changeStaffPassword",
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    principal: Annotated[StaffPrincipal, Depends(get_staff_principal)],
) -> ChangePasswordEnvelope:
    await _store(request).change_password(
        principal,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return ChangePasswordEnvelope(data=ChangePasswordData())


def _token_envelope_with_cookies(
    response: Response,
    tokens: IssuedStaffTokens,
    settings: Settings,
) -> AuthEnvelope:
    now = int(time.time())
    access_expires_in = max(60, tokens.access_expires_at - now)
    refresh_expires_in = max(3_600, tokens.refresh_expires_at - now)
    csrf_token = secrets.token_urlsafe(32)
    cookie_path = _auth_cookie_path(settings)
    response.set_cookie(
        key=settings.staff_refresh_cookie_name,
        value=tokens.refresh_token,
        max_age=refresh_expires_in,
        path=cookie_path,
        secure=settings.staff_auth_cookie_secure,
        httponly=True,
        samesite=settings.staff_auth_cookie_samesite,
    )
    response.set_cookie(
        key=settings.staff_csrf_cookie_name,
        value=csrf_token,
        max_age=refresh_expires_in,
        path=cookie_path,
        secure=settings.staff_auth_cookie_secure,
        httponly=False,
        samesite=settings.staff_auth_cookie_samesite,
    )
    response.headers["X-CSRF-Token"] = csrf_token
    _set_no_store(response)
    return AuthEnvelope(
        data=StaffTokenData(
            access_token=tokens.access_token,
            csrf_token=csrf_token,
            expires_in=access_expires_in,
            refresh_expires_in=refresh_expires_in,
        )
    )


async def _enforce_csrf(
    *,
    request: Request,
    store: AuthStore,
    event_type: str,
    request_ip_hash_value: str,
    supplied_token: str | None,
) -> None:
    settings = request.app.state.settings
    cookie_token = request.cookies.get(settings.staff_csrf_cookie_name)
    valid = bool(
        cookie_token
        and supplied_token
        and 32 <= len(cookie_token) <= 256
        and 32 <= len(supplied_token) <= 256
        and hmac.compare_digest(cookie_token, supplied_token)
    )
    if valid:
        return
    await store.record_security_event(
        event_type=event_type,
        outcome="blocked",
        request_ip_hash=request_ip_hash_value,
        reason_code="csrf_validation_failed",
    )
    raise ApiError(403, "CSRF_VALIDATION_FAILED", "请求安全校验失败，请重新登录")


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    cookie_path = _auth_cookie_path(settings)
    response.delete_cookie(
        key=settings.staff_refresh_cookie_name,
        path=cookie_path,
        secure=settings.staff_auth_cookie_secure,
        httponly=True,
        samesite=settings.staff_auth_cookie_samesite,
    )
    response.delete_cookie(
        key=settings.staff_csrf_cookie_name,
        path=cookie_path,
        secure=settings.staff_auth_cookie_secure,
        httponly=False,
        samesite=settings.staff_auth_cookie_samesite,
    )


def _auth_cookie_path(settings: Settings) -> str:
    root_path = settings.asgi_root_path.rstrip("/")
    prefix = settings.api_prefix.rstrip("/")
    return f"{root_path}{prefix}/auth" or "/auth"


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _current_staff_envelope(identity: StaffIdentity) -> CurrentStaffEnvelope:
    return CurrentStaffEnvelope(
        data=CurrentStaffData(
            user=StaffUserView(
                id=identity.user_id,
                display_name=identity.display_name,
            ),
            membership=StaffMembershipView(
                id=identity.membership_id,
                tenant_id=identity.tenant_id,
                company_id=identity.company_id,
                role=identity.role,
                permissions=identity.permissions,
            ),
            must_change_password=identity.must_change_password,
        )
    )


async def _enforce_auth_rate_limit(
    *,
    request: Request,
    store: AuthStore,
    event_type: str,
    request_ip_hash_value: str,
    checks: tuple[tuple[str, str, int], ...],
    account_hash: str | None = None,
) -> None:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        if request.app.state.settings.app_env == "test":
            return
        await store.record_security_event(
            event_type=event_type,
            outcome="blocked",
            account_hash=account_hash,
            request_ip_hash=request_ip_hash_value,
            reason_code="rate_limit_backend_missing",
        )
        raise ApiError(503, "RATE_LIMIT_UNAVAILABLE", "认证保护服务正在恢复，请稍后重试")

    limiter = RedisRateLimiter(redis)
    for bucket, subject, limit in checks:
        try:
            decision = await limiter.check(
                bucket=bucket,
                subject=subject,
                limit=limit,
                window_seconds=60,
            )
        except RateLimitBackendUnavailable as exc:
            await store.record_security_event(
                event_type=event_type,
                outcome="blocked",
                account_hash=account_hash,
                request_ip_hash=request_ip_hash_value,
                reason_code="rate_limit_backend_unavailable",
            )
            raise ApiError(
                503,
                "RATE_LIMIT_UNAVAILABLE",
                "认证保护服务正在恢复，请稍后重试",
            ) from exc
        if not decision.allowed:
            await store.record_security_event(
                event_type=event_type,
                outcome="blocked",
                account_hash=account_hash,
                request_ip_hash=request_ip_hash_value,
                reason_code=f"rate_limit_{bucket}"[:80],
            )
            raise ApiError(
                429,
                "RATE_LIMITED",
                "请求过于频繁，请稍后重试",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
