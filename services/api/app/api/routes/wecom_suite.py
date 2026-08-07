from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from app.api.errors import ApiError
from app.api.wecom_schemas import WeComOAuthUrl, WeComOAuthUrlEnvelope
from app.integrations.wecom import (
    WeComConfigurationError,
    WeComProviderError,
)
from app.integrations.wecom_crypto import (
    WeComCallbackCrypto,
    WeComCryptoError,
    extract_encrypted_xml,
)
from app.integrations.wecom_suite import WeComSuiteClient
from app.services.wecom_suite_store import WeComSuiteStore

router = APIRouter(prefix="/integrations/wecom/suite", tags=["WeCom Provider"])


def _client(request: Request) -> WeComSuiteClient:
    return WeComSuiteClient(
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
        redis=getattr(request.app.state, "redis", None),
    )


def _store(request: Request) -> WeComSuiteStore:
    return WeComSuiteStore(
        request.app.state.session_factory,
        request.app.state.settings,
    )


def _crypto(request: Request) -> WeComCallbackCrypto:
    settings = request.app.state.settings
    token = settings.wecom_suite_callback_token
    encoding_key = settings.wecom_suite_callback_encoding_aes_key
    suite_id = settings.wecom_suite_id
    if token is None or encoding_key is None or not suite_id:
        raise ApiError(409, "WECOM_SUITE_CALLBACK_NOT_CONFIGURED", "企微服务商回调尚未配置")
    try:
        return WeComCallbackCrypto(
            token=token.get_secret_value(),
            encoding_aes_key=encoding_key.get_secret_value(),
            corp_id=suite_id,
        )
    except WeComCryptoError as exc:
        raise ApiError(
            409,
            "WECOM_SUITE_CALLBACK_NOT_CONFIGURED",
            "企微服务商回调尚未配置",
        ) from exc


def _provider_error(exc: Exception) -> ApiError:
    if isinstance(exc, WeComConfigurationError):
        return ApiError(409, "WECOM_SUITE_NOT_READY", "企微服务商应用尚未收到有效配置或票据")
    if isinstance(exc, WeComProviderError):
        details = (
            {"provider_code": exc.provider_code}
            if exc.provider_code is not None
            else None
        )
        return ApiError(
            502,
            exc.code,
            "企业微信服务商接口暂时不可用",
            details=details,
        )
    return ApiError(500, "WECOM_SUITE_FAILED", "企业微信服务商流程暂时不可用")


async def _issue_install_state(request: Request) -> tuple[str, int]:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise ApiError(503, "WECOM_STATE_STORE_UNAVAILABLE", "授权状态存储暂不可用")
    token = secrets.token_hex(32)
    expires_at = int(time.time()) + request.app.state.settings.wecom_oauth_state_ttl_seconds
    created = await redis.set(
        _install_state_key(token),
        json.dumps({"expires_at": expires_at}, separators=(",", ":")),
        ex=request.app.state.settings.wecom_oauth_state_ttl_seconds,
        nx=True,
    )
    if not created:
        raise ApiError(503, "WECOM_STATE_STORE_UNAVAILABLE", "授权状态存储暂不可用")
    return token, expires_at


async def _consume_install_state(request: Request, token: str) -> None:
    if len(token) != 64 or any(value not in "0123456789abcdef" for value in token):
        raise ApiError(400, "WECOM_INSTALL_STATE_INVALID", "企微安装状态已失效")
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        raise ApiError(503, "WECOM_STATE_STORE_UNAVAILABLE", "授权状态存储暂不可用")
    key = _install_state_key(token)
    getdel = getattr(redis, "getdel", None)
    value = await getdel(key) if callable(getdel) else await redis.get(key)
    if not callable(getdel) and value is not None:
        await redis.delete(key)
    if not isinstance(value, str):
        raise ApiError(400, "WECOM_INSTALL_STATE_INVALID", "企微安装状态已失效")
    try:
        expires_at = int(json.loads(value)["expires_at"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ApiError(400, "WECOM_INSTALL_STATE_INVALID", "企微安装状态已失效") from exc
    if expires_at < int(time.time()):
        raise ApiError(400, "WECOM_INSTALL_STATE_INVALID", "企微安装状态已失效")


def _install_state_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    return f"wecom:suite-install-state:{digest}"


async def _exchange_and_save(request: Request, auth_code: str) -> None:
    grant = await _client(request).exchange_permanent_code(auth_code=auth_code)
    await _store(request).save_authorization(grant)


async def _revoke(request: Request, auth_corpid: str) -> None:
    await _store(request).revoke_authorization(auth_corpid=auth_corpid)


@router.get(
    "/install-url",
    response_model=WeComOAuthUrlEnvelope,
    operation_id="createWeComSuiteInstallUrl",
)
async def create_wecom_suite_install_url(request: Request) -> WeComOAuthUrlEnvelope:
    state, expires_at = await _issue_install_state(request)
    try:
        authorize_url, provider_expires_in = await _client(request).create_install_url(
            state=state
        )
    except (WeComConfigurationError, WeComProviderError) as exc:
        raise _provider_error(exc) from exc
    expires_in = min(
        provider_expires_in,
        max(120, expires_at - int(time.time())),
    )
    return WeComOAuthUrlEnvelope(
        data=WeComOAuthUrl(authorize_url=authorize_url, expires_in=expires_in)
    )


@router.get(
    "/install-complete",
    response_class=RedirectResponse,
    operation_id="completeWeComSuiteInstall",
)
async def complete_wecom_suite_install(
    request: Request,
    auth_code: Annotated[str, Query(min_length=64, max_length=512)],
    state: Annotated[str, Query(min_length=64, max_length=64)],
) -> RedirectResponse:
    await _consume_install_state(request, state)
    try:
        await _exchange_and_save(request, auth_code)
    except (WeComConfigurationError, WeComProviderError) as exc:
        raise _provider_error(exc) from exc
    destination = request.app.state.settings.wecom_suite_success_redirect_uri
    if not destination:
        raise ApiError(
            409,
            "WECOM_SUITE_SUCCESS_REDIRECT_NOT_CONFIGURED",
            "企微安装完成跳转地址尚未配置",
        )
    return RedirectResponse(destination, status_code=303)


@router.get(
    "/callback",
    response_class=PlainTextResponse,
    operation_id="verifyWeComSuiteCallbackUrl",
)
async def verify_wecom_suite_callback_url(
    request: Request,
    msg_signature: Annotated[str, Query(min_length=40, max_length=40)],
    timestamp: Annotated[str, Query(min_length=1, max_length=20)],
    nonce: Annotated[str, Query(min_length=1, max_length=256)],
    echostr: Annotated[str, Query(min_length=1, max_length=4_096)],
) -> PlainTextResponse:
    try:
        value = _crypto(request).decrypt_raw(
            encrypted=echostr,
            signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        ).decode("utf-8")
    except (WeComCryptoError, UnicodeDecodeError) as exc:
        raise ApiError(400, "WECOM_SUITE_CALLBACK_INVALID", "企微服务商回调校验失败") from exc
    return PlainTextResponse(value, headers={"Cache-Control": "no-store"})


@router.post(
    "/callback",
    response_class=PlainTextResponse,
    operation_id="receiveWeComSuiteCallback",
)
async def receive_wecom_suite_callback(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: Annotated[str, Query(min_length=40, max_length=40)],
    timestamp: Annotated[str, Query(min_length=1, max_length=20)],
    nonce: Annotated[str, Query(min_length=1, max_length=256)],
) -> PlainTextResponse:
    body = await request.body()
    if not body or len(body) > 1_048_576:
        raise ApiError(413, "WECOM_SUITE_CALLBACK_TOO_LARGE", "企微服务商回调内容超出限制")
    try:
        encrypted = extract_encrypted_xml(body)
        message = _crypto(request).decrypt(
            encrypted=encrypted,
            signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
    except WeComCryptoError as exc:
        raise ApiError(400, "WECOM_SUITE_CALLBACK_INVALID", "企微服务商回调校验失败") from exc

    info_type = (message.fields.get("InfoType") or "").casefold()
    if info_type == "suite_ticket":
        ticket = message.fields.get("SuiteTicket") or ""
        try:
            await _client(request).store_suite_ticket(ticket)
        except WeComConfigurationError as exc:
            raise _provider_error(exc) from exc
    elif info_type == "create_auth":
        auth_code = message.fields.get("AuthCode") or ""
        if auth_code:
            background_tasks.add_task(_exchange_and_save, request, auth_code)
    elif info_type == "cancel_auth":
        auth_corpid = message.fields.get("AuthCorpId") or ""
        if auth_corpid:
            background_tasks.add_task(_revoke, request, auth_corpid)

    return PlainTextResponse("success", headers={"Cache-Control": "no-store"})


__all__ = ["router"]
