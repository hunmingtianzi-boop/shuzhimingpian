"""Official Account OAuth transport, independent of enterprise membership.

This module only verifies a provider identity. The caller must consume a
single-use, browser-bound state before exchanging a code and must separately
resolve the user's application permissions before issuing a session.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

import httpx

from app.core.config import Settings


class WeChatConfigurationError(RuntimeError):
    pass


class WeChatProviderError(RuntimeError):
    """Provider errors never include codes, tokens, URLs or provider messages."""

    def __init__(self, code: str, *, provider_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.provider_code = provider_code


@dataclass(frozen=True, slots=True)
class WeChatIdentity:
    app_id: str
    open_id: str = field(repr=False)
    union_id: str | None = field(default=None, repr=False)


class WeChatClient:
    """Use snsapi_base for identity; do not depend on a nickname or avatar."""

    def __init__(self, *, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    def _credentials(self) -> tuple[str, str]:
        app_id = self._settings.wechat_app_id
        secret = self._settings.wechat_app_secret
        if not app_id or not re.fullmatch(r"wx[A-Za-z0-9]{16}", app_id) or not secret:
            raise WeChatConfigurationError("wechat_credentials_missing_or_invalid")
        return app_id, secret.get_secret_value()

    def build_oauth_authorize_url(
        self, *, state: str, scope: Literal["snsapi_base", "snsapi_userinfo"] = "snsapi_base"
    ) -> str:
        app_id, _ = self._credentials()
        redirect_uri = self._settings.wechat_oauth_redirect_uri
        if not redirect_uri or any(ord(char) < 33 for char in redirect_uri):
            raise WeChatConfigurationError("wechat_redirect_uri_invalid")
        try:
            parsed = urlsplit(redirect_uri)
            valid = (
                parsed.scheme == "https"
                and parsed.hostname
                and parsed.port in (None, 443)
                and not parsed.username
                and not parsed.password
                and not parsed.fragment
                and not parsed.query
                and "\\" not in redirect_uri
            )
        except ValueError:
            valid = False
        if not valid:
            raise WeChatConfigurationError("wechat_redirect_uri_invalid")
        if not re.fullmatch(r"[A-Za-z0-9]{32,128}", state):
            raise WeChatConfigurationError("wechat_oauth_state_invalid")
        if scope not in {"snsapi_base", "snsapi_userinfo"}:
            raise WeChatConfigurationError("wechat_oauth_scope_invalid")
        query = urlencode(
            {
                "appid": app_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": scope,
                "state": state,
            }
        )
        return f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect"

    async def exchange_code(self, *, code: str) -> WeChatIdentity:
        app_id, secret = self._credentials()
        if not code or len(code) > 512 or any(ord(char) < 33 for char in code):
            raise WeChatProviderError("WECHAT_OAUTH_CODE_INVALID")
        # OAuth codes are single-use. Never retry this request or return the
        # provider's access/refresh tokens to callers or browser clients.
        try:
            response = await self._http.get(
                "https://api.weixin.qq.com/sns/oauth2/access_token",
                params={
                    "appid": app_id,
                    "secret": secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
                timeout=self._settings.wechat_timeout_seconds,
                follow_redirects=False,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            # httpx exceptions can contain the secret-bearing request URL.
            raise WeChatProviderError("WECHAT_OAUTH_UNAVAILABLE") from None
        if not isinstance(payload, dict):
            raise WeChatProviderError("WECHAT_OAUTH_RESPONSE_INVALID")
        error_code = payload.get("errcode", 0)
        if type(error_code) is not int:
            raise WeChatProviderError("WECHAT_OAUTH_RESPONSE_INVALID")
        if error_code != 0:
            raise WeChatProviderError("WECHAT_OAUTH_REJECTED", provider_code=error_code)
        open_id = payload.get("openid")
        union_id = payload.get("unionid")
        if not _valid_identifier(open_id) or (
            union_id is not None and not _valid_identifier(union_id)
        ):
            raise WeChatProviderError("WECHAT_OAUTH_RESPONSE_INVALID")
        if not isinstance(payload.get("access_token"), str) or not payload["access_token"]:
            raise WeChatProviderError("WECHAT_OAUTH_RESPONSE_INVALID")
        return WeChatIdentity(app_id=app_id, open_id=open_id, union_id=union_id)

    async def jsapi_ticket(self, redis: Any) -> str:
        app_id, secret = self._credentials()
        # Credential rotation must invalidate the cache without storing secrets
        # in Redis key names. stable_token does not force-refresh a valid token.
        credential_key = hashlib.sha256(f"{app_id}:{secret}".encode()).hexdigest()
        key = f"wechat:jsapi-ticket:{credential_key}"
        try:
            cached = await redis.get(key)
            if cached:
                return cached.decode() if isinstance(cached, bytes) else str(cached)
        except Exception:
            raise WeChatProviderError("WECHAT_CACHE_UNAVAILABLE") from None
        try:
            token_response = await self._http.post(
                "https://api.weixin.qq.com/cgi-bin/stable_token",
                json={
                    "grant_type": "client_credential",
                    "appid": app_id,
                    "secret": secret,
                    "force_refresh": False,
                },
                timeout=self._settings.wechat_timeout_seconds,
                follow_redirects=False,
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            token = _provider_field(token_payload, "access_token")
            ticket_response = await self._http.get(
                "https://api.weixin.qq.com/cgi-bin/ticket/getticket",
                params={"access_token": token, "type": "jsapi"},
                timeout=self._settings.wechat_timeout_seconds,
                follow_redirects=False,
            )
            ticket_response.raise_for_status()
            payload = ticket_response.json()
            ticket = _provider_field(payload, "ticket")
            expiry = payload.get("expires_in")
            if type(expiry) is not int or expiry <= 60:
                raise WeChatProviderError("WECHAT_JS_SDK_RESPONSE_INVALID")
        except (httpx.HTTPError, ValueError):
            raise WeChatProviderError("WECHAT_JS_SDK_UNAVAILABLE") from None
        try:
            await redis.set(key, ticket, ex=min(expiry - 60, 7_000))
        except Exception:
            raise WeChatProviderError("WECHAT_CACHE_UNAVAILABLE") from None
        return ticket


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value))


def _provider_field(payload: object, key: str) -> str:
    if not isinstance(payload, dict):
        raise WeChatProviderError("WECHAT_JS_SDK_RESPONSE_INVALID")
    error_code = payload.get("errcode", 0)
    if type(error_code) is not int or error_code:
        raise WeChatProviderError(
            "WECHAT_JS_SDK_REJECTED", provider_code=error_code if type(error_code) is int else None
        )
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise WeChatProviderError("WECHAT_JS_SDK_RESPONSE_INVALID")
    return value
