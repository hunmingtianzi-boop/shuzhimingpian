from __future__ import annotations

import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.auth_schemas import AuthEnvelope
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.routes.auth import _token_envelope_with_cookies
from app.api.wecom_schemas import (
    WeComBindingEnvelope,
    WeComBindingRecord,
    WeComOAuthExchangeRequest,
    WeComOAuthUrl,
    WeComOAuthUrlEnvelope,
)
from app.core.request_context import request_id_ctx
from app.core.request_security import request_ip_hash
from app.core.tokens import StaffPrincipal
from app.integrations.wecom import (
    WeComClient,
    WeComConfigurationError,
    WeComDepartment,
    WeComMember,
    WeComProviderError,
)
from app.integrations.wecom_oauth import (
    WeComOAuthStateError,
    WeComOAuthStateManager,
)
from app.integrations.wecom_suite import WeComSuiteClient
from app.services.auth_store import AuthStore
from app.services.wecom_store import WeComStore
from app.services.wecom_suite_store import WeComSuiteStore

router = APIRouter(prefix="/auth/wecom", tags=["WeCom Authentication"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _client(request: Request) -> WeComClient:
    return WeComClient(
        settings=request.app.state.settings,
        http_client=getattr(
            request.app.state, "wecom_http_client", request.app.state.http_client
        ),
        redis=getattr(request.app.state, "redis", None),
    )


def _states(request: Request) -> WeComOAuthStateManager:
    return WeComOAuthStateManager(
        settings=request.app.state.settings,
        redis=getattr(request.app.state, "redis", None),
    )


def _suite_client(request: Request) -> WeComSuiteClient:
    return WeComSuiteClient(
        settings=request.app.state.settings,
        http_client=getattr(
            request.app.state, "wecom_http_client", request.app.state.http_client
        ),
        redis=getattr(request.app.state, "redis", None),
    )


def _suite_store(request: Request) -> WeComSuiteStore:
    return WeComSuiteStore(
        request.app.state.session_factory,
        request.app.state.settings,
    )


def _uses_suite(request: Request) -> bool:
    settings = request.app.state.settings
    if settings.wecom_auth_mode == "third_party":
        return True
    if settings.wecom_auth_mode == "self_built":
        return False
    return bool(settings.wecom_suite_id and settings.wecom_suite_secret)


def _oauth_error(exc: Exception) -> ApiError:
    if isinstance(exc, WeComConfigurationError):
        return ApiError(409, "WECOM_OAUTH_NOT_CONFIGURED", "企业微信登录尚未完成配置")
    if isinstance(exc, WeComOAuthStateError):
        return ApiError(400, "WECOM_OAUTH_STATE_INVALID", "企业微信登录状态已失效，请重试")
    if isinstance(exc, WeComProviderError):
        details = (
            {"provider_code": exc.provider_code}
            if exc.provider_code is not None
            else None
        )
        return ApiError(
            502,
            exc.code,
            "企业微信暂时无法完成身份校验，请稍后重试",
            details=details,
        )
    return ApiError(500, "WECOM_OAUTH_FAILED", "企业微信登录暂时不可用")


async def _oauth_url(
    request: Request,
    *,
    mode: Literal["login", "bind"],
    return_to: str,
    principal: StaffPrincipal | None = None,
) -> WeComOAuthUrlEnvelope:
    try:
        state, expires_at = await _states(request).issue(
            mode=mode,
            principal=principal,
            return_to=return_to,
        )
        authorize_url = (
            _suite_client(request).build_oauth_authorize_url(state=state)
            if _uses_suite(request)
            else _client(request).build_oauth_authorize_url(state=state)
        )
    except (WeComConfigurationError, WeComOAuthStateError) as exc:
        raise _oauth_error(exc) from exc
    return WeComOAuthUrlEnvelope(
        data=WeComOAuthUrl(
            authorize_url=authorize_url,
            expires_in=max(120, expires_at - int(time.time())),
        )
    )


@router.get(
    "/login-url",
    response_model=WeComOAuthUrlEnvelope,
    operation_id="createWeComLoginUrl",
)
async def create_wecom_login_url(
    request: Request,
    return_to: Annotated[str, Query(min_length=1, max_length=500)] = "/",
) -> WeComOAuthUrlEnvelope:
    return await _oauth_url(request, mode="login", return_to=return_to)


@router.get(
    "/bind-url",
    response_model=WeComOAuthUrlEnvelope,
    operation_id="createWeComBindingUrl",
)
async def create_wecom_binding_url(
    request: Request,
    principal: StaffDependency,
    return_to: Annotated[str, Query(min_length=1, max_length=500)] = "/",
) -> WeComOAuthUrlEnvelope:
    return await _oauth_url(
        request,
        mode="bind",
        return_to=return_to,
        principal=principal,
    )


@router.post(
    "/login",
    response_model=AuthEnvelope,
    operation_id="loginWithWeCom",
)
async def login_with_wecom(
    payload: WeComOAuthExchangeRequest,
    request: Request,
    response: Response,
) -> AuthEnvelope:
    try:
        state = await _states(request).consume(payload.state)
        if state.mode != "login":
            raise WeComOAuthStateError("wrong oauth mode")
        corp_id: str | None = None
        allow_bootstrap = True
        enterprise_name: str
        if _uses_suite(request):
            suite_client = _suite_client(request)
            identity = await suite_client.get_user_identity(code=payload.code)
            authorization = await _suite_store(request).get_authorization(
                auth_corpid=identity.corp_id
            )
            member = await suite_client.get_member(
                auth_corpid=authorization.auth_corpid,
                permanent_code=authorization.permanent_code,
                user_id=identity.user_id,
            )
            departments = await suite_client.list_departments(
                auth_corpid=authorization.auth_corpid,
                permanent_code=authorization.permanent_code,
            )
            corp_id = authorization.auth_corpid
            allow_bootstrap = (
                authorization.authorizer_user_id is not None
                and authorization.authorizer_user_id == identity.user_id
            )
            enterprise_name = authorization.corp_name or _enterprise_name(departments)
        else:
            client = _client(request)
            identity = await client.get_user_identity(code=payload.code)
            member = await client.get_member(user_id=identity.user_id)
            departments = await client.list_departments()
            enterprise_name = _enterprise_name(departments)
        _require_active_member(member)
    except (WeComConfigurationError, WeComOAuthStateError, WeComProviderError) as exc:
        raise _oauth_error(exc) from exc
    store = WeComStore(
        request.app.state.session_factory,
        request.app.state.settings,
    )
    resolved = await store.resolve_or_bootstrap_identity(
        member=member,
        enterprise_name=enterprise_name,
        corp_id=corp_id,
        allow_bootstrap=allow_bootstrap,
    )
    authentication = await AuthStore(
        request.app.state.session_factory,
        request.app.state.settings,
    ).authenticate_trusted_identity(
        user_id=resolved.user_id,
        membership_id=resolved.membership_id,
        tenant_id=resolved.tenant_id,
        company_id=resolved.company_id,
        event_type="staff.wecom_login",
        account_hash=resolved.account_hash,
        request_ip_hash=request_ip_hash(request, request.app.state.settings),
    )
    return _token_envelope_with_cookies(
        response,
        authentication.tokens,
        request.app.state.settings,
    )


@router.post(
    "/bind",
    response_model=WeComBindingEnvelope,
    operation_id="bindCurrentStaffToWeCom",
)
async def bind_current_staff_to_wecom(
    payload: WeComOAuthExchangeRequest,
    request: Request,
) -> WeComBindingEnvelope:
    try:
        state = await _states(request).consume(payload.state)
        if state.mode != "bind":
            raise WeComOAuthStateError("wrong oauth mode")
        corp_id: str | None = None
        if _uses_suite(request):
            suite_client = _suite_client(request)
            identity = await suite_client.get_user_identity(code=payload.code)
            authorization = await _suite_store(request).get_authorization(
                auth_corpid=identity.corp_id
            )
            await _suite_store(request).require_scope(
                auth_corpid=authorization.auth_corpid,
                tenant_id=state.tenant_id,
                company_id=state.company_id,
            )
            member = await suite_client.get_member(
                auth_corpid=authorization.auth_corpid,
                permanent_code=authorization.permanent_code,
                user_id=identity.user_id,
            )
            corp_id = authorization.auth_corpid
        else:
            identity = await _client(request).get_user_identity(code=payload.code)
            member = await _client(request).get_member(user_id=identity.user_id)
        _require_active_member(member)
    except (WeComConfigurationError, WeComOAuthStateError, WeComProviderError) as exc:
        raise _oauth_error(exc) from exc
    binding = await WeComStore(
        request.app.state.session_factory,
        request.app.state.settings,
    ).bind_member(
        state=state,
        member=member,
        trace_id=request_id_ctx.get(),
        corp_id=corp_id,
    )
    return WeComBindingEnvelope(
        data=WeComBindingRecord(
            id=binding.id,
            membership_id=binding.membership_id,
            member_name=member.name,
        )
    )


def _require_active_member(member: WeComMember) -> None:
    if member.status is not None and member.status != 1:
        raise ApiError(403, "WECOM_MEMBER_INACTIVE", "企业微信成员未激活或已停用")


def _enterprise_name(departments: tuple[WeComDepartment, ...]) -> str:
    """Choose the corporation root exposed by the application's address book."""

    if not departments:
        return "企业微信企业"
    department_ids = {item.department_id for item in departments}
    roots = [
        item
        for item in departments
        if item.parent_id in (None, 0) or item.parent_id not in department_ids
    ]
    candidates = roots or list(departments)
    selected = min(
        candidates,
        key=lambda item: (
            item.order is None,
            item.order if item.order is not None else 0,
            item.department_id,
        ),
    )
    return selected.name.strip()[:200] or "企业微信企业"


__all__ = ["router"]
