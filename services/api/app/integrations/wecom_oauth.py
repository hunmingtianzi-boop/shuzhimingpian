from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from app.core.config import Settings
from app.core.tokens import StaffPrincipal


class WeComOAuthStateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WeComOAuthState:
    mode: Literal["login", "bind"]
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    token_id: uuid.UUID
    return_to: str
    user_id: uuid.UUID | None = None
    membership_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None


class WeComOAuthStateManager:
    def __init__(self, *, settings: Settings, redis: Any | None) -> None:
        self._settings = settings
        self._redis = redis

    async def issue(
        self,
        *,
        mode: Literal["login", "bind"],
        principal: StaffPrincipal | None = None,
        return_to: str = "/",
    ) -> tuple[str, int]:
        tenant_id, company_id = self._scope()
        if mode == "bind":
            if principal is None:
                raise WeComOAuthStateError("staff session required")
            if principal.tenant_id != tenant_id or principal.company_id != company_id:
                raise WeComOAuthStateError("staff scope does not match WeCom configuration")
        if self._redis is None:
            raise WeComOAuthStateError("oauth state store unavailable")
        safe_return_to = _safe_return_to(return_to)
        now = int(time.time())
        expires_at = now + self._settings.wecom_oauth_state_ttl_seconds
        token_id = uuid.uuid4()
        state_token = secrets.token_hex(32)
        payload: dict[str, object] = {
            "token_id": str(token_id),
            "mode": mode,
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "return_to": safe_return_to,
            "expires_at": expires_at,
        }
        if principal is not None:
            payload.update(
                user_id=str(principal.user_id),
                membership_id=str(principal.membership_id),
                session_id=str(principal.session_id),
            )
        created = await self._redis.set(
            self._nonce_key(state_token),
            json.dumps(payload, sort_keys=True, separators=(",", ":")),
            ex=self._settings.wecom_oauth_state_ttl_seconds,
            nx=True,
        )
        if not created:
            raise WeComOAuthStateError("oauth state store unavailable")
        return state_token, expires_at

    async def consume(self, token: str) -> WeComOAuthState:
        if self._redis is None:
            raise WeComOAuthStateError("oauth state store unavailable")
        if len(token) != 64 or any(
            character not in "0123456789abcdef" for character in token
        ):
            raise WeComOAuthStateError("invalid oauth state")
        stored = await self._consume_nonce(token)
        if not isinstance(stored, str):
            raise WeComOAuthStateError("oauth state expired or already used")
        try:
            payload = json.loads(stored)
            if not isinstance(payload, dict):
                raise ValueError("invalid state payload")
            mode = payload["mode"]
            if mode not in {"login", "bind"}:
                raise ValueError("invalid mode")
            expires_at = int(payload["expires_at"])
            if expires_at < int(time.time()):
                raise ValueError("state expired")
            token_id = uuid.UUID(payload["token_id"])
            state = WeComOAuthState(
                mode=mode,
                tenant_id=uuid.UUID(payload["tenant_id"]),
                company_id=uuid.UUID(payload["company_id"]),
                token_id=token_id,
                return_to=_safe_return_to(str(payload.get("return_to", "/"))),
                user_id=(uuid.UUID(payload["user_id"]) if mode == "bind" else None),
                membership_id=(
                    uuid.UUID(payload["membership_id"]) if mode == "bind" else None
                ),
                session_id=(uuid.UUID(payload["session_id"]) if mode == "bind" else None),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise WeComOAuthStateError("invalid oauth state") from exc
        if (state.tenant_id, state.company_id) != self._scope():
            raise WeComOAuthStateError("oauth state scope mismatch")
        return state

    async def _consume_nonce(self, token: str) -> object:
        key = self._nonce_key(token)
        getdel = getattr(self._redis, "getdel", None)
        if callable(getdel):
            return await getdel(key)
        value = await self._redis.get(key)
        if value is not None:
            await self._redis.delete(key)
        return value

    def _scope(self) -> tuple[uuid.UUID, uuid.UUID]:
        tenant_id = self._settings.wecom_tenant_id
        company_id = self._settings.wecom_company_id
        if tenant_id is None or company_id is None:
            raise WeComOAuthStateError("WeCom identity scope is not configured")
        return tenant_id, company_id

    @staticmethod
    def _nonce_key(token: str) -> str:
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        return f"wecom:oauth-state:{digest}"


def _safe_return_to(value: str) -> str:
    normalized = value.strip() or "/"
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or "\\" in normalized
        or "\r" in normalized
        or "\n" in normalized
        or len(normalized) > 500
    ):
        raise WeComOAuthStateError("invalid return path")
    return normalized


__all__ = [
    "WeComOAuthState",
    "WeComOAuthStateError",
    "WeComOAuthStateManager",
]
