from __future__ import annotations

import hashlib
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI

from app.api.errors import ApiError, api_error_handler
from app.api.routes import wechat_auth
from app.core.config import Settings
from app.core.tokens import IssuedStaffTokens
from app.integrations.wechat import WeChatClient, WeChatConfigurationError, WeChatProviderError
from app.integrations.wechat_oauth import WeChatOAuthStateError, WeChatOAuthStates
from app.services.wechat_js_sdk import public_share_url, share_signature


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, *, ex, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def get(self, key):
        return self.values.get(key)

    async def getdel(self, key):
        return self.values.pop(key, None)


def settings(**kwargs):
    return Settings(
        _env_file=None,
        app_env="test",
        wechat_app_id="wx0123456789abcdef",
        wechat_app_secret="test-secret",  # noqa: S106
        wechat_oauth_redirect_uri="https://cards.example/admin/wechat/callback",
        public_card_base_url="https://cards.example",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_authorization_uses_official_account_not_wecom():
    async with httpx.AsyncClient() as http:
        client = WeChatClient(settings=settings(), http_client=http)
        parsed = urlsplit(client.build_oauth_authorize_url(state="a" * 64))
        query = parse_qs(parsed.query)
        assert parsed.netloc == "open.weixin.qq.com"
        assert query["scope"] == ["snsapi_base"]
        assert query["appid"] == ["wx0123456789abcdef"]
        assert query["redirect_uri"] == ["https://cards.example/admin/wechat/callback"]
        assert "secret" not in query and "agentid" not in query
        assert parsed.fragment == "wechat_redirect"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "redirect",
    [
        "http://cards.example/callback",
        "https://user@cards.example",
        "https://cards.example/#fragment",
        "https://cards.example/?x=1",
        "https://cards.example:invalid/callback",
    ],
)
async def test_invalid_callback_configuration_is_rejected(redirect):
    config = settings().model_copy(update={"wechat_oauth_redirect_uri": redirect})
    async with httpx.AsyncClient() as http:
        with pytest.raises(WeChatConfigurationError):
            WeChatClient(settings=config, http_client=http).build_oauth_authorize_url(
                state="a" * 64
            )


@pytest.mark.asyncio
async def test_exchange_returns_only_identity_and_never_retries_provider_rejections():
    calls = []

    def provider(request):
        calls.append(request)
        assert request.url.host == "api.weixin.qq.com"
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "openid": "user-one",
                    "unionid": "union-one",
                    "access_token": "private-token",
                },
            )
        return httpx.Response(200, json={"errcode": 40029, "errmsg": "secret=do-not-log"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        client = WeChatClient(settings=settings(), http_client=http)
        identity = await client.exchange_code(code="one-use-code")
        assert identity.open_id == "user-one" and identity.union_id == "union-one"
        assert "user-one" not in repr(identity) and "private-token" not in repr(identity)
        with pytest.raises(WeChatProviderError) as failure:
            await client.exchange_code(code="expired-code")
        assert failure.value.provider_code == 40029
        assert "do-not-log" not in str(failure.value)
        assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"openid": "x"},
        {"openid": 1, "access_token": "t"},
        {"errcode": "0", "openid": "x", "access_token": "t"},
    ],
)
async def test_malformed_identity_cannot_create_an_account(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as http:
        with pytest.raises(WeChatProviderError):
            await WeChatClient(settings=settings(), http_client=http).exchange_code(code="code")


@pytest.mark.asyncio
async def test_state_is_browser_bound_single_use_and_app_scoped():
    redis = MemoryRedis()
    states = WeChatOAuthStates(redis, "app-one")
    token, browser = await states.issue("/admin/cards")
    assert await states.consume(token, browser) == "/admin/cards"
    with pytest.raises(WeChatOAuthStateError):
        await states.consume(token, browser)
    token, browser = await states.issue("/admin/cards")
    with pytest.raises(WeChatOAuthStateError):
        await WeChatOAuthStates(redis, "app-two").consume(token, browser)
    assert await states.consume(token, browser) == "/admin/cards"
    token, browser = await states.issue("/admin/cards")
    with pytest.raises(WeChatOAuthStateError):
        await states.consume(token, "b" * 64)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example",
        "//evil.example",
        "/%2Fevil.example",
        "/%5Cevil.example",
        "/cards%0Aheader",
    ],
)
async def test_state_rejects_external_redirects(target):
    with pytest.raises(WeChatOAuthStateError):
        await WeChatOAuthStates(MemoryRedis(), "app").issue(target)


@pytest.mark.asyncio
async def test_ticket_is_cached_and_uses_stable_token():
    calls = []

    def provider(request):
        calls.append(request)
        if request.method == "POST":
            assert json.loads(request.content)["force_refresh"] is False
            return httpx.Response(200, json={"access_token": "server-token"})
        return httpx.Response(200, json={"errcode": 0, "ticket": "ticket", "expires_in": 7200})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        client = WeChatClient(settings=settings(), http_client=http)
        redis = MemoryRedis()
        assert await client.jsapi_ticket(redis) == "ticket"
        assert await client.jsapi_ticket(redis) == "ticket"
        assert len(calls) == 2
        assert "test-secret" not in str(redis.values)


def test_signature_preserves_query_and_removes_fragment():
    url = public_share_url("https://cards.example/c/abc?from=friend#page", "abc", settings())
    assert url == "https://cards.example/c/abc?from=friend"
    config = share_signature(app_id="app", ticket="ticket", url=url, timestamp=123, nonce="nonce")
    expected = hashlib.sha1(
        f"jsapi_ticket=ticket&noncestr=nonce&timestamp=123&url={url}".encode(),
        usedforsecurity=False,
    ).hexdigest()
    assert config.signature == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/c/abc",
        "https://cards.example/c/other",
        "https://cards.example/admin",
        "https://user@cards.example/c/abc",
    ],
)
def test_signature_rejects_other_origins_and_cards(url):
    with pytest.raises(ApiError):
        public_share_url(url, "abc", settings())


@pytest.mark.asyncio
async def test_login_cookie_state_session_and_replay(monkeypatch):
    app = FastAPI()
    app.include_router(wechat_auth.router, prefix="/api/v1")
    app.add_exception_handler(ApiError, api_error_handler)
    app.state.settings = settings()
    app.state.redis = MemoryRedis()
    app.state.session_factory = object()
    monkeypatch.setattr(wechat_auth, "_rate_limit", AsyncMock())
    provider_calls = []

    def provider(request):
        provider_calls.append(request)
        return httpx.Response(
            200, json={"openid": "verified-user", "access_token": "provider-token"}
        )

    resolved = SimpleNamespace(
        user_id="u", membership_id="m", tenant_id="t", company_id="c", account_hash="hash"
    )
    store = SimpleNamespace(provision=AsyncMock(return_value=resolved))
    now = int(time.time())
    tokens = IssuedStaffTokens(
        access_token="session-access",  # noqa: S106 - test token
        refresh_token="session-refresh",  # noqa: S106 - test token
        access_expires_at=now + 900,
        refresh_expires_at=now + 86400,
    )
    auth = SimpleNamespace(
        authenticate_trusted_identity=AsyncMock(return_value=SimpleNamespace(tokens=tokens))
    )
    monkeypatch.setattr(wechat_auth, "WeChatStore", lambda *args: store)
    monkeypatch.setattr(wechat_auth, "AuthStore", lambda *args: auth)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as provider_http:
        app.state.http_client = provider_http
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://cards.example"
        ) as http:
            started = await http.get("/api/v1/auth/wechat/login-url?return_to=/admin/cards")
            assert started.status_code == 200
            assert "HttpOnly" in started.headers["set-cookie"]
            state = parse_qs(urlsplit(started.json()["data"]["authorize_url"]).query)["state"][0]
            result = await http.post(
                "/api/v1/auth/wechat/login", json={"code": "code", "state": state}
            )
            assert result.status_code == 200
            assert result.json()["data"]["return_to"] == "/admin/cards"
            assert result.json()["data"]["access_token"] == "session-access"  # noqa: S105 - test token
            assert "provider-token" not in result.text and "verified-user" not in result.text
            replay = await http.post(
                "/api/v1/auth/wechat/login", json={"code": "code", "state": state}
            )
            assert replay.status_code == 400
            assert len(provider_calls) == 1
            store.provision.assert_awaited_once()
