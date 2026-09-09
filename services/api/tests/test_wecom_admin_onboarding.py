from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import Response

from app.api.errors import ApiError
from app.api.routes import wecom_auth
from app.api.wecom_schemas import WeComOAuthExchangeRequest
from app.core.config import Settings
from app.integrations.wecom import WeComMember, WeComProviderError
from app.integrations.wecom_suite import WeComSuiteClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "admins, expected",
    [
        ([{"userid": "member", "auth_type": 1}], True),
        ([{"userid": "other", "auth_type": 1}], False),
        ([{"userid": "member", "auth_type": 0}], False),
        ([{"userid": "member", "auth_type": True}], False),
        ([], False),
    ],
)
async def test_management_authority_uses_current_corp_scoped_api(
    admins: list[dict[str, object]],
    expected: bool,
) -> None:
    calls: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.method == "POST"
        assert request.url.path == "/cgi-bin/agent/get_admin_list"
        assert dict(request.url.params) == {"access_token": "corp-token"}
        if len(calls) == 1:
            return httpx.Response(200, json={"errcode": 40014})
        return httpx.Response(200, json={"errcode": 0, "admin": admins})

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as http:
        connector = WeComSuiteClient(
            settings=Settings(_env_file=None, app_env="test"),
            http_client=http,
        )
        connector.corp_access_token = AsyncMock(return_value="corp-token")
        assert (
            await connector.is_application_admin(
                auth_corpid="corp",
                permanent_code="grant",
                user_id="member",
            )
            is expected
        )
        connector.corp_access_token.assert_awaited_with(
            auth_corpid="corp",
            permanent_code="grant",
            force_refresh=True,
        )
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("authorizer", [None, "former-installer"])
async def test_login_auto_creates_verified_admin_without_installation_authorizer(
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
    authorizer: str | None,
) -> None:
    suite, store, auth, request = _mock_login(monkeypatch, existing=existing, authorizer=authorizer)
    result = await wecom_auth.login_with_wecom(
        WeComOAuthExchangeRequest(code="code", state="a" * 64),
        request,
        Response(),
    )
    assert result == "authenticated"
    auth.authenticate_trusted_identity.assert_awaited_once()
    if existing:
        suite.is_application_admin.assert_not_awaited()
        store.resolve_or_bootstrap_identity.assert_not_awaited()
    else:
        suite.is_application_admin.assert_awaited_once_with(
            auth_corpid="corp",
            permanent_code="grant",
            user_id="member",
        )
        assert store.resolve_or_bootstrap_identity.await_args.kwargs["allow_bootstrap"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_failure", [False, True])
async def test_unverified_member_cannot_create_admin_or_get_session(
    monkeypatch: pytest.MonkeyPatch,
    provider_failure: bool,
) -> None:
    suite, store, auth, request = _mock_login(monkeypatch, existing=False, authorizer="member")
    if provider_failure:
        suite.is_application_admin.side_effect = WeComProviderError("WECOM_UNAVAILABLE")
    else:
        suite.is_application_admin.return_value = False
        store.resolve_or_bootstrap_identity.side_effect = ApiError(403, "ADMIN_REQUIRED", "denied")
    with pytest.raises(ApiError):
        await wecom_auth.login_with_wecom(
            WeComOAuthExchangeRequest(code="code", state="a" * 64),
            request,
            Response(),
        )
    auth.authenticate_trusted_identity.assert_not_awaited()
    if provider_failure:
        store.resolve_or_bootstrap_identity.assert_not_awaited()
    else:
        assert store.resolve_or_bootstrap_identity.await_args.kwargs["allow_bootstrap"] is False


def _mock_login(monkeypatch: pytest.MonkeyPatch, *, existing: bool, authorizer: str | None):
    resolved = SimpleNamespace(
        user_id="user",
        membership_id="membership",
        tenant_id="tenant",
        company_id="company",
        account_hash="hash",
    )
    store = SimpleNamespace(
        resolve_identity=AsyncMock(return_value=resolved),
        resolve_or_bootstrap_identity=AsyncMock(return_value=resolved),
    )
    if not existing:
        store.resolve_identity.side_effect = ApiError(403, "WECOM_ACCOUNT_NOT_BOUND", "unbound")
    suite = SimpleNamespace(
        get_user_identity=AsyncMock(return_value=SimpleNamespace(corp_id="corp", user_id="member")),
        get_member=AsyncMock(
            return_value=WeComMember(
                user_id="member",
                name="Admin",
                departments=(),
                position=None,
                avatar_url=None,
                status=1,
            )
        ),
        list_departments=AsyncMock(return_value=()),
        is_application_admin=AsyncMock(return_value=True),
    )
    authorization = SimpleNamespace(
        auth_corpid="corp",
        permanent_code="grant",
        corp_name="Association",
        authorizer_user_id=authorizer,
    )
    auth = SimpleNamespace(
        authenticate_trusted_identity=AsyncMock(return_value=SimpleNamespace(tokens="tokens"))
    )
    monkeypatch.setattr(wecom_auth, "_uses_suite", lambda request: True)
    monkeypatch.setattr(
        wecom_auth,
        "_states",
        lambda request: SimpleNamespace(
            consume=AsyncMock(return_value=SimpleNamespace(mode="login"))
        ),
    )
    monkeypatch.setattr(wecom_auth, "_suite_client", lambda request: suite)
    monkeypatch.setattr(
        wecom_auth,
        "_suite_store",
        lambda request: SimpleNamespace(get_authorization=AsyncMock(return_value=authorization)),
    )
    monkeypatch.setattr(wecom_auth, "WeComStore", lambda *args: store)
    monkeypatch.setattr(wecom_auth, "AuthStore", lambda *args: auth)
    monkeypatch.setattr(wecom_auth, "request_ip_hash", lambda *args: None)
    monkeypatch.setattr(wecom_auth, "_token_envelope_with_cookies", lambda *args: "authenticated")
    request = Request(
        {
            "type": "http",
            "app": SimpleNamespace(state=SimpleNamespace(settings=None, session_factory=None)),
        }
    )
    return suite, store, auth, request
