from __future__ import annotations

import base64
import hashlib
import struct
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pydantic import ValidationError

from app.api.routes.wecom_auth import _enterprise_name
from app.core.config import Settings
from app.core.tokens import StaffPrincipal
from app.integrations.wecom import WeComClient, WeComDepartment, WeComProviderError
from app.integrations.wecom_crypto import (
    WeComCallbackCrypto,
    WeComCryptoError,
    parse_wecom_xml,
)
from app.integrations.wecom_oauth import (
    WeComOAuthStateError,
    WeComOAuthStateManager,
)
from app.integrations.wecom_suite import WeComSuiteClient


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(
        self, key: str, value: str, *, ex: int, nx: bool = False
    ) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def getdel(self, key: str) -> str | None:
        self.ttls.pop(key, None)
        return self.values.pop(key, None)

    async def delete(self, key: str) -> None:
        self.ttls.pop(key, None)
        self.values.pop(key, None)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "wecom_corp_id": "ww1234567890abcdef",
        "wecom_agent_id": 1000002,
        "wecom_app_secret": "test-only-wecom-secret",
    }
    values.update(overrides)
    return Settings(**values)


def test_wecom_core_settings_are_all_or_none() -> None:
    with pytest.raises(ValidationError, match="must be configured together"):
        Settings(_env_file=None, app_env="test", wecom_corp_id="ww-only")

    settings = Settings(
        _env_file=None,
        app_env="test",
        wecom_corp_id="",
        wecom_agent_id="",
        wecom_app_secret="",
        wecom_tenant_id="",
        wecom_company_id="",
    )
    assert settings.wecom_corp_id is None
    assert settings.wecom_agent_id is None
    assert settings.wecom_app_secret is None
    assert settings.wecom_tenant_id is None
    assert settings.wecom_company_id is None


def test_wecom_suite_settings_require_secret_for_third_party_auth() -> None:
    with pytest.raises(ValidationError, match="requires suite credentials"):
        Settings(
            _env_file=None,
            app_env="test",
            wecom_auth_mode="third_party",
            wecom_suite_id="wwsuite123456",
        )

    settings = Settings(
        _env_file=None,
        app_env="test",
        wecom_auth_mode="third_party",
        wecom_suite_id="wwsuite123456",
        wecom_suite_secret="test-only-suite-secret",  # noqa: S106 - fixture
        wecom_suite_install_redirect_uri="https://example.test/install-complete",
        wecom_suite_oauth_redirect_uri="https://example.test/wecom/callback",
    )
    assert settings.wecom_suite_secret is not None
    assert settings.wecom_auth_mode == "third_party"


def test_wecom_suite_callback_can_be_verified_before_secret_is_issued() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        wecom_auth_mode="auto",
        wecom_suite_id="wwsuite123456",
        wecom_suite_callback_token="callback-token",  # noqa: S106 - protocol fixture
        wecom_suite_callback_encoding_aes_key="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        wecom_suite_callback_corp_id="wwprovider123456",
    )

    assert settings.wecom_suite_id == "wwsuite123456"
    assert settings.wecom_suite_secret is None
    assert settings.wecom_suite_callback_token is not None
    assert settings.wecom_suite_callback_corp_id == "wwprovider123456"


@pytest.mark.asyncio
async def test_wecom_suite_install_and_per_corp_tokens_are_separately_cached() -> None:
    requests: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/get_suite_token"):
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "suite_access_token": "suite-token",
                    "expires_in": 7200,
                },
            )
        if request.url.path.endswith("/get_pre_auth_code"):
            assert request.url.params["suite_access_token"] == "suite-" + "token"
            return httpx.Response(
                200,
                json={"errcode": 0, "pre_auth_code": "pre-auth-code", "expires_in": 1200},
            )
        if request.url.path.endswith("/set_session_info"):
            return httpx.Response(200, json={"errcode": 0})
        if request.url.path.endswith("/get_corp_token"):
            return httpx.Response(
                200,
                json={"errcode": 0, "access_token": "corp-token", "expires_in": 7200},
            )
        raise AssertionError(f"unexpected provider path: {request.url.path}")

    settings = Settings(
        _env_file=None,
        app_env="test",
        wecom_suite_id="wwsuite123456",
        wecom_suite_secret="test-only-suite-secret",  # noqa: S106 - fixture
        wecom_suite_install_redirect_uri="https://example.test/install-complete",
    )
    redis = MemoryRedis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        connector = WeComSuiteClient(settings=settings, http_client=client, redis=redis)
        await connector.store_suite_ticket("suite-ticket")
        install_url, expires_in = await connector.create_install_url(state="a" * 64)
        first = await connector.corp_access_token(
            auth_corpid="wwcorp123456",
            permanent_code="permanent-code",
        )
        second = await connector.corp_access_token(
            auth_corpid="wwcorp123456",
            permanent_code="permanent-code",
        )

    assert "suite_id=wwsuite123456" in install_url
    assert "state=" + "a" * 64 in install_url
    assert expires_in == 1200
    assert first == second == "corp-token"
    assert [request.url.path for request in requests].count(
        "/cgi-bin/service/get_corp_token"
    ) == 1


@pytest.mark.asyncio
async def test_wecom_suite_message_uses_corp_token_and_authorized_agent() -> None:
    async def provider(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cgi-bin/message/send"
        assert request.url.params["access_token"] == "corp-token"  # noqa: S105
        assert request.content
        payload = request.content.decode("utf-8")
        assert "suite-user-id" in payload
        assert "1000002" in payload
        return httpx.Response(
            200,
            json={"errcode": 0, "errmsg": "ok", "msgid": "message-1"},
        )

    settings = Settings(
        _env_file=None,
        app_env="test",
        wecom_suite_id="wwsuite123456",
        wecom_suite_secret="test-only-suite-secret",  # noqa: S106 - fixture
    )
    redis = MemoryRedis()
    suite_digest = hashlib.sha256(b"wwsuite123456").hexdigest()[:20]
    corp_digest = hashlib.sha256(b"wwcorp123456").hexdigest()[:20]
    redis.values[
        f"wecom:corp-access-token:{suite_digest}:{corp_digest}"
    ] = "corp-token"
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        result = await WeComSuiteClient(
            settings=settings,
            http_client=client,
            redis=redis,
        ).send_text(
            auth_corpid="wwcorp123456",
            permanent_code="permanent-code",
            agent_id=1000002,
            user_id="suite-user-id",
            content="有人正在查看名片",
        )

    assert result.message_id == "message-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider_payload",
    [
        {"errcode": 0, "errmsg": "ok", "unlicenseduser": "suite-user-id"},
        {"errcode": 0, "errmsg": "ok", "invaliduser": ["suite-user-id"]},
        {"errcode": 0, "errmsg": "ok"},
    ],
)
async def test_wecom_suite_message_rejects_false_delivery_acknowledgements(
    provider_payload: dict[str, object],
) -> None:
    async def provider(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=provider_payload)

    settings = Settings(
        _env_file=None,
        app_env="test",
        wecom_suite_id="wwsuite123456",
        wecom_suite_secret="test-only-suite-secret",  # noqa: S106 - fixture
    )
    redis = MemoryRedis()
    suite_digest = hashlib.sha256(b"wwsuite123456").hexdigest()[:20]
    corp_digest = hashlib.sha256(b"wwcorp123456").hexdigest()[:20]
    redis.values[
        f"wecom:corp-access-token:{suite_digest}:{corp_digest}"
    ] = "corp-token"
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        connector = WeComSuiteClient(settings=settings, http_client=client, redis=redis)
        with pytest.raises(
            WeComProviderError,
            match="WECOM_INVALID_RECIPIENT|WECOM_INVALID_RESPONSE",
        ):
            await connector.send_text(
                auth_corpid="wwcorp123456",
                permanent_code="permanent-code",
                agent_id=1000002,
                user_id="suite-user-id",
                content="有人正在查看名片",
            )


@pytest.mark.asyncio
async def test_wecom_probe_validates_token_and_agent_and_caches_token() -> None:
    requests: list[httpx.Request] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/gettoken"):
            assert request.url.params["corpid"] == "ww1234567890abcdef"
            assert request.url.params["corpsecret"] == "test-only-wecom-secret"
            return httpx.Response(
                200,
                json={"errcode": 0, "errmsg": "ok", "access_token": "token-1", "expires_in": 7200},
            )
        assert request.url.path.endswith("/agent/get")
        assert request.url.params["access_token"] == "token-1"  # noqa: S105 - fixture
        assert request.url.params["agentid"] == "1000002"
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", "name": "数智名片"})

    redis = MemoryRedis()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        result = await WeComClient(
            settings=_settings(), http_client=client, redis=redis
        ).probe()

    assert result.agent_name == "数智名片"
    assert len(requests) == 2
    assert next(iter(redis.values.values())) == "token-1"
    assert next(iter(redis.ttls.values())) == 6900


@pytest.mark.asyncio
async def test_wecom_test_message_uses_cached_token_and_rejects_invalid_user() -> None:
    async def provider(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/message/send")
        body = request.content.decode("utf-8")
        assert "test-user" in body
        return httpx.Response(
            200,
            json={"errcode": 0, "errmsg": "ok", "invaliduser": "test-user"},
        )

    redis = MemoryRedis()
    digest = hashlib.sha256(b"ww1234567890abcdef").hexdigest()[:20]
    redis.values[f"wecom:access-token:{digest}"] = "cached-token"
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        connector = WeComClient(settings=_settings(), http_client=client, redis=redis)
        with pytest.raises(WeComProviderError, match="WECOM_INVALID_RECIPIENT"):
            await connector.send_text(user_id="test-user", content="连接测试")


@pytest.mark.asyncio
async def test_wecom_internal_oauth_uses_self_built_app_identity_endpoint() -> None:
    async def provider(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/cgi-bin/user/getuserinfo"
        assert request.url.params["access_token"] == "cached-" + "token"
        assert request.url.params["code"] == "oauth-code"
        return httpx.Response(
            200,
            json={
                "errcode": 0,
                "errmsg": "ok",
                "UserId": "ZhouZiHan",
                "DeviceId": "device-1",
            },
        )

    redis = MemoryRedis()
    digest = hashlib.sha256(b"ww1234567890abcdef").hexdigest()[:20]
    redis.values[f"wecom:access-token:{digest}"] = "cached-token"
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        identity = await WeComClient(
            settings=_settings(), http_client=client, redis=redis
        ).get_user_identity(code="oauth-code")

    assert identity.user_id == "ZhouZiHan"
    assert identity.device_id == "device-1"


@pytest.mark.asyncio
async def test_wecom_provider_error_does_not_include_provider_message() -> None:
    async def provider(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errcode": 40013, "errmsg": "invalid corpid with private detail"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        connector = WeComClient(settings=_settings(), http_client=client)
        with pytest.raises(WeComProviderError) as exc_info:
            await connector.access_token()

    assert exc_info.value.code == "WECOM_PROVIDER_REJECTED"
    assert exc_info.value.provider_code == 40013
    assert "private detail" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_wecom_oauth_state_is_scoped_one_time_and_builds_official_url() -> None:
    tenant_id = uuid.uuid4()
    company_id = uuid.uuid4()
    settings = _settings(
        wecom_tenant_id=tenant_id,
        wecom_company_id=company_id,
        wecom_oauth_redirect_uri="http://127.0.0.1:4174/wecom/callback",
    )
    redis = MemoryRedis()
    manager = WeComOAuthStateManager(settings=settings, redis=redis)
    principal = StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=tenant_id,
        company_id=company_id,
        role="company_admin",
        permissions=(),
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )
    state_token, _expires_at = await manager.issue(
        mode="bind",
        principal=principal,
        return_to="/settings/integrations",
    )
    assert len(state_token) == 64
    assert state_token.isalnum()
    async with httpx.AsyncClient() as client:
        authorize_url = WeComClient(
            settings=settings,
            http_client=client,
            redis=redis,
        ).build_oauth_authorize_url(state=state_token)
    assert authorize_url.startswith("https://open.weixin.qq.com/connect/oauth2/authorize?")
    assert "scope=snsapi_base" in authorize_url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A4174%2Fwecom%2Fcallback" in authorize_url

    state = await manager.consume(state_token)
    assert state.mode == "bind"
    assert state.membership_id == principal.membership_id
    assert state.return_to == "/settings/integrations"
    with pytest.raises(WeComOAuthStateError, match="already used"):
        await manager.consume(state_token)


@pytest.mark.asyncio
async def test_wecom_member_and_department_reads_use_visible_scope() -> None:
    paths: list[str] = []

    async def provider(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/user/get"):
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "errmsg": "ok",
                    "userid": "zhouzihan",
                    "name": "周子涵",
                    "department": [1],
                    "position": "负责人",
                    "status": 1,
                },
            )
        return httpx.Response(
            200,
            json={
                "errcode": 0,
                "errmsg": "ok",
                "department": [
                    {"id": 1, "name": "夜霜曦雪", "parentid": 0, "order": 1}
                ],
            },
        )

    redis = MemoryRedis()
    digest = hashlib.sha256(b"ww1234567890abcdef").hexdigest()[:20]
    redis.values[f"wecom:access-token:{digest}"] = "cached-token"
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        connector = WeComClient(settings=_settings(), http_client=client, redis=redis)
        member = await connector.get_member(user_id="zhouzihan")
        departments = await connector.list_departments()

    assert member.name == "周子涵"
    assert member.departments == (1,)
    assert departments[0].name == "夜霜曦雪"
    assert paths == ["/cgi-bin/user/get", "/cgi-bin/department/list"]


def test_wecom_callback_crypto_verifies_decrypts_and_rejects_entities() -> None:
    token = "callback-token"  # noqa: S105 - protocol fixture, not a credential
    corp_id = "ww1234567890abcdef"
    key = b"0123456789abcdef0123456789abcdef"
    encoding_key = base64.b64encode(key).decode("ascii").rstrip("=")
    xml = (
        b"<xml><ToUserName>ww1234567890abcdef</ToUserName>"
        b"<FromUserName>zhouzihan</FromUserName><CreateTime>123</CreateTime>"
        b"<MsgType>event</MsgType><Event>change_external_contact</Event></xml>"
    )
    encrypted = _encrypt_wecom_fixture(key=key, corp_id=corp_id, message=xml)
    timestamp = "1720000000"
    nonce = "fixture-nonce"
    signature = hashlib.sha1(  # noqa: S324 - mandated by the WeCom protocol
        "".join(sorted((token, timestamp, nonce, encrypted))).encode("utf-8")
    ).hexdigest()
    crypto = WeComCallbackCrypto(
        token=token,
        encoding_aes_key=encoding_key,
        corp_id=corp_id,
    )
    message = crypto.decrypt(
        encrypted=encrypted,
        signature=signature,
        timestamp=timestamp,
        nonce=nonce,
    )
    assert message.xml == xml
    assert message.fields["Event"] == "change_external_contact"
    with pytest.raises(WeComCryptoError, match="signature"):
        crypto.decrypt(
            encrypted=encrypted,
            signature="0" * 40,
            timestamp=timestamp,
            nonce=nonce,
        )
    with pytest.raises(WeComCryptoError):
        parse_wecom_xml(b"<!DOCTYPE xml [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><xml/>")


def test_wecom_enterprise_name_prefers_root_department() -> None:
    assert _enterprise_name(
        (
            WeComDepartment(2, "销售部", 1, 1),
            WeComDepartment(1, "夜霜曦雪", 0, 1),
        )
    ) == "夜霜曦雪"


@pytest.mark.asyncio
async def test_wecom_login_state_does_not_require_precreated_scope() -> None:
    settings = _settings(
        wecom_tenant_id=None,
        wecom_company_id=None,
        wecom_oauth_redirect_uri="https://yeshuangxixue.cn/c/admin/wecom/callback",
    )
    redis = MemoryRedis()
    manager = WeComOAuthStateManager(settings=settings, redis=redis)
    token, _expires_at = await manager.issue(mode="login", return_to="/overview")
    state = await manager.consume(token)
    assert state.mode == "login"
    assert state.tenant_id is None
    assert state.company_id is None


def _encrypt_wecom_fixture(*, key: bytes, corp_id: str, message: bytes) -> str:
    raw = b"0123456789abcdef" + struct.pack("!I", len(message)) + message + corp_id.encode()
    padding = 32 - (len(raw) % 32)
    padded = raw + bytes((padding,)) * padding
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode("ascii")
