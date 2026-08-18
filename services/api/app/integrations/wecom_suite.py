from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.integrations.wecom import (
    WeComConfigurationError,
    WeComDepartment,
    WeComMember,
    WeComMessageResult,
    WeComProviderError,
    build_wecom_template_card_payload,
    parse_wecom_message_result,
)


@dataclass(frozen=True, slots=True)
class WeComSuiteIdentity:
    corp_id: str
    user_id: str
    device_id: str | None


@dataclass(frozen=True, slots=True)
class WeComSuiteAuthorizationGrant:
    auth_corpid: str
    corp_name: str
    permanent_code: str
    agent_id: int | None
    authorizer_user_id: str | None
    metadata: dict[str, object]


class WeComSuiteClient:
    """Provider-application client with suite and per-corporation token caches."""

    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient,
        redis: Any | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._redis = redis

    @property
    def suite_id(self) -> str:
        suite_id, _secret = self._credentials()
        return suite_id

    def _credentials(self) -> tuple[str, str]:
        secret = self._settings.wecom_suite_secret
        if not self._settings.wecom_suite_id or secret is None:
            raise WeComConfigurationError("wecom_suite_not_configured")
        return self._settings.wecom_suite_id, secret.get_secret_value()

    def build_oauth_authorize_url(self, *, state: str) -> str:
        suite_id, _secret = self._credentials()
        redirect_uri = self._settings.wecom_suite_oauth_redirect_uri
        if not redirect_uri:
            raise WeComConfigurationError("wecom_suite_oauth_not_configured")
        self._validate_state(state)
        return (
            "https://open.weixin.qq.com/connect/oauth2/authorize?"
            + urlencode(
                {
                    "appid": suite_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": "snsapi_base",
                    "state": state,
                }
            )
            + "#wechat_redirect"
        )

    async def create_install_url(self, *, state: str) -> tuple[str, int]:
        suite_id, _secret = self._credentials()
        redirect_uri = self._settings.wecom_suite_install_redirect_uri
        if not redirect_uri:
            raise WeComConfigurationError("wecom_suite_install_not_configured")
        self._validate_state(state)
        suite_token = await self.suite_access_token()
        payload = await self._request_json(
            "GET",
            "/cgi-bin/service/get_pre_auth_code",
            params={"suite_access_token": suite_token},
        )
        pre_auth_code = payload.get("pre_auth_code")
        expires_in = payload.get("expires_in")
        if not isinstance(pre_auth_code, str) or not pre_auth_code:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        await self._request_json(
            "POST",
            "/cgi-bin/service/set_session_info",
            params={"suite_access_token": suite_token},
            json={
                "pre_auth_code": pre_auth_code,
                "session_info": {
                    "appid": [],
                    "auth_type": (
                        1 if self._settings.wecom_suite_auth_type == "test" else 0
                    ),
                },
            },
        )
        install_url = "https://open.work.weixin.qq.com/3rdapp/install?" + urlencode(
            {
                "suite_id": suite_id,
                "pre_auth_code": pre_auth_code,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return install_url, max(120, int(expires_in or 1_200))

    async def store_suite_ticket(self, ticket: str) -> None:
        suite_id, _secret = self._credentials()
        normalized = ticket.strip()
        if not normalized or len(normalized) > 1_024 or self._redis is None:
            raise WeComConfigurationError("wecom_suite_ticket_store_unavailable")
        await self._redis.set(self._ticket_key(suite_id), normalized, ex=2_100)
        await self._redis.delete(self._suite_token_key(suite_id))

    async def suite_access_token(self, *, force_refresh: bool = False) -> str:
        suite_id, suite_secret = self._credentials()
        if self._redis is None:
            raise WeComConfigurationError("wecom_suite_ticket_store_unavailable")
        token_key = self._suite_token_key(suite_id)
        if not force_refresh:
            cached = await self._redis.get(token_key)
            if cached:
                return str(cached)
        ticket = await self._redis.get(self._ticket_key(suite_id))
        if not ticket:
            raise WeComConfigurationError("wecom_suite_ticket_missing")
        payload = await self._request_json(
            "POST",
            "/cgi-bin/service/get_suite_token",
            json={
                "suite_id": suite_id,
                "suite_secret": suite_secret,
                "suite_ticket": str(ticket),
            },
        )
        token = payload.get("suite_access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(token, str) or not token:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        await self._redis.set(token_key, token, ex=max(60, int(expires_in or 7_200) - 300))
        return token

    async def exchange_permanent_code(
        self, *, auth_code: str
    ) -> WeComSuiteAuthorizationGrant:
        suite_token = await self.suite_access_token()
        payload = await self._request_json(
            "POST",
            "/cgi-bin/service/get_permanent_code",
            params={"suite_access_token": suite_token},
            json={"auth_code": auth_code},
        )
        permanent_code = payload.get("permanent_code")
        corp = payload.get("auth_corp_info")
        if not isinstance(permanent_code, str) or not permanent_code or not isinstance(corp, dict):
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        auth_corpid = corp.get("corpid")
        corp_name = corp.get("corp_name")
        if not isinstance(auth_corpid, str) or not auth_corpid:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        if not isinstance(corp_name, str) or not corp_name:
            corp_name = "企业微信企业"
        agent_id: int | None = None
        auth_info = payload.get("auth_info")
        if isinstance(auth_info, dict):
            agents = auth_info.get("agent")
            if isinstance(agents, list) and agents and isinstance(agents[0], dict):
                raw_agent_id = agents[0].get("agentid")
                agent_id = raw_agent_id if isinstance(raw_agent_id, int) else None
        authorizer_user_id: str | None = None
        auth_user = payload.get("auth_user_info")
        if isinstance(auth_user, dict):
            raw_user_id = auth_user.get("userid")
            if isinstance(raw_user_id, str) and raw_user_id:
                authorizer_user_id = raw_user_id
        safe_metadata = {
            "auth_corp_info": corp,
            "auth_info": auth_info if isinstance(auth_info, dict) else {},
            "auth_user_info": auth_user if isinstance(auth_user, dict) else {},
        }
        return WeComSuiteAuthorizationGrant(
            auth_corpid=auth_corpid,
            corp_name=corp_name[:200],
            permanent_code=permanent_code,
            agent_id=agent_id,
            authorizer_user_id=authorizer_user_id,
            metadata=safe_metadata,
        )

    async def get_user_identity(self, *, code: str) -> WeComSuiteIdentity:
        suite_token = await self.suite_access_token()
        payload = await self._request_json(
            "GET",
            self._settings.wecom_suite_userinfo_path,
            params={"access_token": suite_token, "code": code},
        )
        corp_id = payload.get("CorpId") or payload.get("corpid")
        user_id = payload.get("UserId") or payload.get("userid")
        if (
            not isinstance(corp_id, str)
            or not corp_id
            or not isinstance(user_id, str)
            or not user_id
        ):
            raise WeComProviderError("WECOM_INTERNAL_MEMBER_REQUIRED")
        device_id = payload.get("DeviceId") or payload.get("deviceid")
        return WeComSuiteIdentity(
            corp_id=corp_id,
            user_id=user_id,
            device_id=device_id if isinstance(device_id, str) and device_id else None,
        )

    async def corp_access_token(
        self,
        *,
        auth_corpid: str,
        permanent_code: str,
        force_refresh: bool = False,
    ) -> str:
        if self._redis is None:
            raise WeComConfigurationError("wecom_suite_token_store_unavailable")
        cache_key = self._corp_token_key(auth_corpid)
        if not force_refresh:
            cached = await self._redis.get(cache_key)
            if cached:
                return str(cached)
        suite_token = await self.suite_access_token()
        payload = await self._request_json(
            "POST",
            "/cgi-bin/service/get_corp_token",
            params={"suite_access_token": suite_token},
            json={"auth_corpid": auth_corpid, "permanent_code": permanent_code},
        )
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(token, str) or not token:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        await self._redis.set(cache_key, token, ex=max(60, int(expires_in or 7_200) - 300))
        return token

    async def get_member(
        self,
        *,
        auth_corpid: str,
        permanent_code: str,
        user_id: str,
    ) -> WeComMember:
        token = await self.corp_access_token(
            auth_corpid=auth_corpid,
            permanent_code=permanent_code,
        )
        payload = await self._request_json(
            "GET",
            "/cgi-bin/user/get",
            params={"access_token": token, "userid": user_id},
        )
        returned_id = payload.get("userid")
        if not isinstance(returned_id, str) or not returned_id:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        raw_departments = payload.get("department")
        departments = (
            tuple(item for item in raw_departments if isinstance(item, int))
            if isinstance(raw_departments, list)
            else ()
        )
        return WeComMember(
            user_id=returned_id,
            name=self._optional_text(payload.get("name")),
            departments=departments,
            position=self._optional_text(payload.get("position")),
            avatar_url=self._optional_text(payload.get("avatar")),
            status=payload.get("status") if isinstance(payload.get("status"), int) else None,
        )

    async def send_text(
        self,
        *,
        auth_corpid: str,
        permanent_code: str,
        agent_id: int,
        user_id: str,
        content: str,
    ) -> WeComMessageResult:
        if agent_id <= 0:
            raise WeComConfigurationError("wecom_suite_agent_not_configured")
        token = await self.corp_access_token(
            auth_corpid=auth_corpid,
            permanent_code=permanent_code,
        )
        payload = await self._request_json(
            "POST",
            "/cgi-bin/message/send",
            params={"access_token": token},
            json={
                "touser": user_id,
                "msgtype": "text",
                "agentid": agent_id,
                "text": {"content": content},
                "safe": 0,
                "enable_id_trans": 0,
                "enable_duplicate_check": 1,
                "duplicate_check_interval": 1800,
            },
        )
        return parse_wecom_message_result(payload)

    async def send_template_card(
        self,
        *,
        auth_corpid: str,
        permanent_code: str,
        agent_id: int,
        user_id: str,
        title: str,
        subtitle: str,
        summary: str,
        emphasis_title: str,
        emphasis_description: str,
        details: tuple[tuple[str, str], ...],
        url: str,
        action_text: str = "查看访问报告",
    ) -> WeComMessageResult:
        if agent_id <= 0:
            raise WeComConfigurationError("wecom_suite_agent_not_configured")
        token = await self.corp_access_token(
            auth_corpid=auth_corpid,
            permanent_code=permanent_code,
        )
        payload = await self._request_json(
            "POST",
            "/cgi-bin/message/send",
            params={"access_token": token},
            json=build_wecom_template_card_payload(
                user_id=user_id,
                agent_id=agent_id,
                title=title,
                subtitle=subtitle,
                summary=summary,
                emphasis_title=emphasis_title,
                emphasis_description=emphasis_description,
                details=details,
                url=url,
                action_text=action_text,
            ),
        )
        return parse_wecom_message_result(payload)

    async def list_departments(
        self,
        *,
        auth_corpid: str,
        permanent_code: str,
    ) -> tuple[WeComDepartment, ...]:
        token = await self.corp_access_token(
            auth_corpid=auth_corpid,
            permanent_code=permanent_code,
        )
        payload = await self._request_json(
            "GET",
            "/cgi-bin/department/list",
            params={"access_token": token},
        )
        raw_departments = payload.get("department")
        if not isinstance(raw_departments, list):
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        result: list[WeComDepartment] = []
        for item in raw_departments:
            if not isinstance(item, dict):
                raise WeComProviderError("WECOM_INVALID_RESPONSE")
            item_id = item.get("id")
            name = item.get("name")
            if not isinstance(item_id, int) or not isinstance(name, str) or not name:
                raise WeComProviderError("WECOM_INVALID_RESPONSE")
            parent_id = item.get("parentid")
            order = item.get("order")
            result.append(
                WeComDepartment(
                    department_id=item_id,
                    name=name,
                    parent_id=parent_id if isinstance(parent_id, int) else None,
                    order=order if isinstance(order, int) else None,
                )
            )
        return tuple(result)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json: dict[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            response = await self._http.request(
                method,
                f"{self._settings.wecom_api_base_url}{path}",
                params=params,
                json=json,
                timeout=self._settings.wecom_timeout_seconds,
            )
            response.raise_for_status()
            payload: object = response.json()
        except (httpx.HTTPError, ValueError, TimeoutError) as exc:
            raise WeComProviderError("WECOM_UNAVAILABLE") from exc
        if not isinstance(payload, dict):
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        provider_code = payload.get("errcode")
        if provider_code is not None and not isinstance(provider_code, int):
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        if isinstance(provider_code, int) and provider_code != 0:
            raise WeComProviderError(
                "WECOM_PROVIDER_REJECTED",
                provider_code=provider_code,
            )
        return payload

    @staticmethod
    def _validate_state(state: str) -> None:
        if not state.isascii() or not state.isalnum() or not 1 <= len(state) <= 128:
            raise WeComConfigurationError("wecom_suite_state_invalid")

    @staticmethod
    def _optional_text(value: object) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]

    def _ticket_key(self, suite_id: str) -> str:
        return f"wecom:suite-ticket:{self._digest(suite_id)}"

    def _suite_token_key(self, suite_id: str) -> str:
        return f"wecom:suite-access-token:{self._digest(suite_id)}"

    def _corp_token_key(self, corp_id: str) -> str:
        suite_id, _secret = self._credentials()
        return f"wecom:corp-access-token:{self._digest(suite_id)}:{self._digest(corp_id)}"


__all__ = [
    "WeComSuiteAuthorizationGrant",
    "WeComSuiteClient",
    "WeComSuiteIdentity",
]
