from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from typing import Any
from urllib.parse import unquote


class WeChatOAuthStateError(ValueError):
    pass


def safe_return_to(value: str) -> str:
    decoded = unquote(value)
    if (
        len(value) > 500
        or not value.startswith("/")
        or decoded.startswith("//")
        or "\\" in decoded
        or any(ord(char) < 32 for char in decoded)
    ):
        raise WeChatOAuthStateError("invalid return path")
    return value


class WeChatOAuthStates:
    ttl = 600

    def __init__(self, redis: Any, app_id: str) -> None:
        self._redis = redis
        self._app_id = app_id

    async def issue(self, return_to: str) -> tuple[str, str]:
        return_to = safe_return_to(return_to)
        token, browser_secret = secrets.token_hex(32), secrets.token_hex(32)
        payload = json.dumps(
            {
                "return_to": return_to,
                "browser_hash": hashlib.sha256(browser_secret.encode()).hexdigest(),
            }
        )
        try:
            saved = await self._redis.set(self._key(token), payload, ex=self.ttl, nx=True)
        except Exception:
            raise WeChatOAuthStateError("state store unavailable") from None
        if not saved:
            raise WeChatOAuthStateError("state store unavailable")
        return token, browser_secret

    async def consume(self, token: str, browser_secret: str | None) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", token) or not browser_secret:
            raise WeChatOAuthStateError("invalid state")
        if not re.fullmatch(r"[0-9a-f]{64}", browser_secret):
            raise WeChatOAuthStateError("invalid browser binding")
        try:
            # GETDEL must be atomic; no read/delete fallback permits replay.
            raw = await self._redis.getdel(self._key(token))
            payload = json.loads(raw)
            expected = hashlib.sha256(browser_secret.encode()).hexdigest()
            if not hmac.compare_digest(payload["browser_hash"], expected):
                raise ValueError("browser mismatch")
            return safe_return_to(payload["return_to"])
        except Exception:
            raise WeChatOAuthStateError("state expired, used or browser mismatch") from None

    def _key(self, token: str) -> str:
        digest = hashlib.sha256(f"{self._app_id}:{token}".encode()).hexdigest()
        return f"wechat:oauth-state:{digest}"
