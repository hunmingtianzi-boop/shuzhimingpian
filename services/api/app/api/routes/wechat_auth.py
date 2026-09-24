from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api.errors import ApiError
from app.api.routes.auth import _enforce_auth_rate_limit, _token_envelope_with_cookies
from app.api.wechat_schemas import (
    WeChatAvailability,
    WeChatAvailabilityEnvelope,
    WeChatLoginEnvelope,
    WeChatLoginUrl,
    WeChatLoginUrlEnvelope,
    WeChatOAuthExchange,
    WeChatTokenData,
)
from app.core.request_security import request_ip_hash
from app.integrations.wechat import WeChatClient, WeChatConfigurationError, WeChatProviderError
from app.integrations.wechat_oauth import WeChatOAuthStateError, WeChatOAuthStates
from app.services.auth_store import AuthStore
from app.services.wechat_store import WeChatStore

router = APIRouter(prefix="/auth/wechat", tags=["WeChat Auth"])
_COOKIE = "cf_wechat_oauth"


def _client(request: Request) -> WeChatClient:
    return WeChatClient(
        settings=request.app.state.settings, http_client=request.app.state.http_client
    )


def _states(request: Request) -> WeChatOAuthStates:
    return WeChatOAuthStates(
        getattr(request.app.state, "redis", None), request.app.state.settings.wechat_app_id or ""
    )


def _cookie_path(request: Request) -> str:
    settings = request.app.state.settings
    return f"{settings.asgi_root_path.rstrip('/')}{settings.api_prefix}/auth/wechat"


async def _rate_limit(request: Request) -> None:
    settings = request.app.state.settings
    ip_hash = request_ip_hash(request, settings)
    await _enforce_auth_rate_limit(
        request=request,
        store=AuthStore(request.app.state.session_factory, settings),
        event_type="staff.wechat_login",
        request_ip_hash_value=ip_hash,
        checks=(("wechat-login-ip", ip_hash, settings.staff_login_ip_rate_limit_per_minute),),
    )


@router.get(
    "/availability",
    response_model=WeChatAvailabilityEnvelope,
    operation_id="getWeChatLoginAvailability",
)
async def availability(request: Request, response: Response) -> WeChatAvailabilityEnvelope:
    response.headers["Cache-Control"] = "no-store"
    try:
        _client(request).build_oauth_authorize_url(state="0" * 64)
        enabled = True
    except WeChatConfigurationError:
        enabled = False
    return WeChatAvailabilityEnvelope(data=WeChatAvailability(enabled=enabled))


@router.get(
    "/login-url", response_model=WeChatLoginUrlEnvelope, operation_id="createWeChatLoginUrl"
)
async def login_url(
    request: Request,
    response: Response,
    return_to: Annotated[str, Query(min_length=1, max_length=500)] = "/",
) -> WeChatLoginUrlEnvelope:
    await _rate_limit(request)
    try:
        client = _client(request)
        client.build_oauth_authorize_url(state="0" * 64)
        state, browser_secret = await _states(request).issue(return_to)
        url = client.build_oauth_authorize_url(state=state)
    except WeChatConfigurationError:
        raise ApiError(409, "WECHAT_NOT_CONFIGURED", "微信服务号登录尚未完成配置") from None
    except WeChatOAuthStateError:
        raise ApiError(400, "WECHAT_STATE_UNAVAILABLE", "微信登录无法发起，请稍后重试") from None
    response.set_cookie(
        _COOKIE,
        browser_secret,
        max_age=600,
        path=_cookie_path(request),
        httponly=True,
        samesite="lax",
        secure=request.app.state.settings.staff_auth_cookie_secure,
    )
    response.headers["Cache-Control"] = "no-store"
    return WeChatLoginUrlEnvelope(data=WeChatLoginUrl(authorize_url=url))


@router.post("/login", response_model=WeChatLoginEnvelope, operation_id="loginWithWeChat")
async def login(
    payload: WeChatOAuthExchange,
    request: Request,
    response: Response,
) -> WeChatLoginEnvelope:
    await _rate_limit(request)
    try:
        return_to = await _states(request).consume(payload.state, request.cookies.get(_COOKIE))
        identity = await _client(request).exchange_code(code=payload.code)
    except WeChatOAuthStateError:
        raise ApiError(400, "WECHAT_OAUTH_STATE_INVALID", "微信登录已失效，请重新进入") from None
    except WeChatConfigurationError:
        raise ApiError(409, "WECHAT_NOT_CONFIGURED", "微信服务号登录尚未完成配置") from None
    except WeChatProviderError as exc:
        raise ApiError(502, exc.code, "微信暂时无法完成登录，请重新进入") from None
    settings = request.app.state.settings
    resolved = await WeChatStore(request.app.state.session_factory, settings).provision(identity)
    authentication = await AuthStore(
        request.app.state.session_factory,
        settings,
    ).authenticate_trusted_identity(
        user_id=resolved.user_id,
        membership_id=resolved.membership_id,
        tenant_id=resolved.tenant_id,
        company_id=resolved.company_id,
        account_hash=resolved.account_hash,
        event_type="staff.wechat_login",
        request_ip_hash=request_ip_hash(request, settings),
    )
    envelope = _token_envelope_with_cookies(response, authentication.tokens, settings)
    response.delete_cookie(
        _COOKIE,
        path=_cookie_path(request),
        httponly=True,
        samesite="lax",
        secure=settings.staff_auth_cookie_secure,
    )
    return WeChatLoginEnvelope(
        data=WeChatTokenData(
            **envelope.data.model_dump(),
            return_to=return_to,
        )
    )
