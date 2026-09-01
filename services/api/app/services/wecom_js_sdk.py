from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.api.errors import ApiError
from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class WeComJSSDKSignatures:
    url: str
    timestamp: int
    nonce_str: str
    config_signature: str
    agent_config_signature: str


def normalize_public_card_js_sdk_url(
    *,
    value: str,
    slug: str,
    settings: Settings,
) -> str:
    """Allow signatures only for the exact public card URL on our own origin."""

    raw = value.strip()
    if not raw or len(raw) > 2_048 or "\\" in raw or any(ord(char) < 32 for char in raw):
        raise ApiError(422, "WECOM_JS_SDK_URL_INVALID", "企微签名页面地址无效")
    actual = urlsplit(raw)
    public_base = urlsplit(settings.public_card_base_url)
    expected_path = f"{public_base.path.rstrip('/')}/c/{slug}"
    if (
        actual.scheme != public_base.scheme
        or actual.netloc != public_base.netloc
        or actual.username is not None
        or actual.password is not None
        or actual.path.rstrip("/") != expected_path.rstrip("/")
    ):
        raise ApiError(422, "WECOM_JS_SDK_URL_INVALID", "企微签名仅支持当前公开名片地址")
    if settings.app_env != "local" and actual.scheme != "https":
        raise ApiError(422, "WECOM_JS_SDK_HTTPS_REQUIRED", "企微签名页面必须使用 HTTPS")
    return urlunsplit((actual.scheme, actual.netloc, actual.path, actual.query, ""))


def build_wecom_js_sdk_signatures(
    *,
    url: str,
    config_ticket: str,
    agent_config_ticket: str,
    timestamp: int | None = None,
    nonce_str: str | None = None,
) -> WeComJSSDKSignatures:
    resolved_timestamp = timestamp or int(time.time())
    resolved_nonce = nonce_str or secrets.token_hex(16)
    return WeComJSSDKSignatures(
        url=url,
        timestamp=resolved_timestamp,
        nonce_str=resolved_nonce,
        config_signature=_signature(
            ticket=config_ticket,
            nonce_str=resolved_nonce,
            timestamp=resolved_timestamp,
            url=url,
        ),
        agent_config_signature=_signature(
            ticket=agent_config_ticket,
            nonce_str=resolved_nonce,
            timestamp=resolved_timestamp,
            url=url,
        ),
    )


def _signature(*, ticket: str, nonce_str: str, timestamp: int, url: str) -> str:
    canonical = (
        f"jsapi_ticket={ticket}&noncestr={nonce_str}"
        f"&timestamp={timestamp}&url={url}"
    )
    return hashlib.sha1(canonical.encode("utf-8"), usedforsecurity=False).hexdigest()


__all__ = [
    "WeComJSSDKSignatures",
    "build_wecom_js_sdk_signatures",
    "normalize_public_card_js_sdk_url",
]
