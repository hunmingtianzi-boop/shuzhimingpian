import hashlib
import secrets
import time
from urllib.parse import urlsplit, urlunsplit

from app.api.errors import ApiError
from app.api.wechat_schemas import WeChatShareConfig
from app.core.config import Settings


def public_share_url(value: str, slug: str, settings: Settings) -> str:
    if not value or len(value) > 2_048 or "\\" in value or any(ord(c) < 32 for c in value):
        raise ApiError(422, "WECHAT_JS_SDK_URL_INVALID", "微信签名地址无效")
    try:
        actual, base = urlsplit(value), urlsplit(settings.public_card_base_url)
        valid = (
            actual.scheme == base.scheme
            and actual.netloc == base.netloc
            and not actual.username
            and not actual.password
            and actual.path.rstrip("/") == f"{base.path.rstrip('/')}/c/{slug}"
            and (settings.app_env in {"local", "test"} or actual.scheme == "https")
        )
    except ValueError:
        valid = False
    if not valid:
        raise ApiError(422, "WECHAT_JS_SDK_URL_INVALID", "只能签名当前公开名片地址")
    return urlunsplit((actual.scheme, actual.netloc, actual.path, actual.query, ""))


def share_signature(
    *, app_id: str, ticket: str, url: str, timestamp: int | None = None, nonce: str | None = None
) -> WeChatShareConfig:
    timestamp = timestamp if timestamp is not None else int(time.time())
    nonce = nonce or secrets.token_hex(16)
    canonical = f"jsapi_ticket={ticket}&noncestr={nonce}&timestamp={timestamp}&url={url}"
    return WeChatShareConfig(
        app_id=app_id,
        timestamp=timestamp,
        nonce_str=nonce,
        signature=hashlib.sha1(canonical.encode(), usedforsecurity=False).hexdigest(),
    )
