from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from app.api.errors import ApiError
from app.integrations.wecom_crypto import (
    WeComCallbackCrypto,
    WeComCryptoError,
    extract_encrypted_xml,
)
from app.services.wecom_store import WeComStore

router = APIRouter(prefix="/integrations/wecom", tags=["WeCom Callbacks"])


def _crypto(request: Request) -> WeComCallbackCrypto:
    settings = request.app.state.settings
    token = settings.wecom_callback_token
    encoding_key = settings.wecom_callback_encoding_aes_key
    corp_id = settings.wecom_corp_id
    if token is None or encoding_key is None or not corp_id:
        raise ApiError(409, "WECOM_CALLBACK_NOT_CONFIGURED", "企业微信回调尚未配置")
    try:
        return WeComCallbackCrypto(
            token=token.get_secret_value(),
            encoding_aes_key=encoding_key.get_secret_value(),
            corp_id=corp_id,
        )
    except WeComCryptoError as exc:
        raise ApiError(409, "WECOM_CALLBACK_NOT_CONFIGURED", "企业微信回调尚未配置") from exc


def _invalid_callback() -> ApiError:
    return ApiError(400, "WECOM_CALLBACK_INVALID", "企业微信回调校验失败")


@router.get(
    "/callback",
    response_class=PlainTextResponse,
    operation_id="verifyWeComCallbackUrl",
)
async def verify_wecom_callback_url(
    request: Request,
    msg_signature: Annotated[str, Query(min_length=40, max_length=40)],
    timestamp: Annotated[str, Query(min_length=1, max_length=20)],
    nonce: Annotated[str, Query(min_length=1, max_length=256)],
    echostr: Annotated[str, Query(min_length=1, max_length=4_096)],
) -> PlainTextResponse:
    try:
        challenge = _crypto(request).decrypt_raw(
            encrypted=echostr,
            signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
        value = challenge.decode("utf-8")
    except (WeComCryptoError, UnicodeDecodeError) as exc:
        raise _invalid_callback() from exc
    return PlainTextResponse(value, headers={"Cache-Control": "no-store"})


@router.post(
    "/callback",
    response_class=PlainTextResponse,
    operation_id="receiveWeComCallback",
)
async def receive_wecom_callback(
    request: Request,
    msg_signature: Annotated[str, Query(min_length=40, max_length=40)],
    timestamp: Annotated[str, Query(min_length=1, max_length=20)],
    nonce: Annotated[str, Query(min_length=1, max_length=256)],
) -> PlainTextResponse:
    body = await request.body()
    if not body or len(body) > 1_048_576:
        raise ApiError(413, "WECOM_CALLBACK_TOO_LARGE", "企业微信回调内容超出限制")
    try:
        encrypted = extract_encrypted_xml(body)
        message = _crypto(request).decrypt(
            encrypted=encrypted,
            signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
        )
    except WeComCryptoError as exc:
        raise _invalid_callback() from exc
    store = WeComStore(
        request.app.state.session_factory,
        request.app.state.settings,
    )
    await store.record_callback(xml=message.xml, fields=message.fields)
    return PlainTextResponse("success", headers={"Cache-Control": "no-store"})


__all__ = ["router"]
