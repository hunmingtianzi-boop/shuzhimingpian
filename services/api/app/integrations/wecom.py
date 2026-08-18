from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings


class WeComConfigurationError(RuntimeError):
    """Raised when the connector is used before all pilot credentials exist."""


class WeComProviderError(RuntimeError):
    """A sanitized provider failure safe to translate into an API error."""

    def __init__(self, code: str, *, provider_code: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.provider_code = provider_code


@dataclass(frozen=True, slots=True)
class WeComProbeResult:
    corp_name: str | None
    agent_name: str | None


@dataclass(frozen=True, slots=True)
class WeComMessageResult:
    message_id: str | None


def build_wecom_text_card_payload(
    *,
    user_id: str,
    agent_id: int,
    title: str,
    description: str,
    url: str,
    button_text: str = "查看报告",
) -> dict[str, object]:
    """Build a clickable application card accepted by the WeCom message API."""

    normalized_title = title.strip()
    normalized_description = description.strip()
    normalized_url = url.strip()
    normalized_button = button_text.strip() or "查看报告"
    if (
        not user_id.strip()
        or agent_id <= 0
        or not normalized_title
        or not normalized_description
        or not normalized_url.startswith(("https://", "http://"))
    ):
        raise WeComConfigurationError("wecom_text_card_invalid")
    return {
        "touser": user_id,
        "msgtype": "textcard",
        "agentid": agent_id,
        "textcard": {
            "title": normalized_title[:128],
            "description": normalized_description[:512],
            "url": normalized_url[:2_048],
            "btntxt": normalized_button[:4],
        },
        "safe": 0,
        "enable_id_trans": 0,
        "enable_duplicate_check": 1,
        "duplicate_check_interval": 1_800,
    }


def parse_wecom_message_result(payload: dict[str, object]) -> WeComMessageResult:
    """Reject provider acknowledgements that did not accept the target member."""

    rejected_fields = ("invaliduser", "unlicenseduser")
    for field in rejected_fields:
        value = payload.get(field)
        if (isinstance(value, str) and value.strip()) or (
            isinstance(value, list) and len(value) > 0
        ):
            raise WeComProviderError("WECOM_INVALID_RECIPIENT")
    message_id = payload.get("msgid")
    if not isinstance(message_id, str) or not message_id.strip():
        raise WeComProviderError("WECOM_INVALID_RESPONSE")
    return WeComMessageResult(message_id=message_id)


@dataclass(frozen=True, slots=True)
class WeComUserIdentity:
    user_id: str
    device_id: str | None


@dataclass(frozen=True, slots=True)
class WeComMember:
    user_id: str
    name: str | None
    departments: tuple[int, ...]
    position: str | None
    avatar_url: str | None
    status: int | None


@dataclass(frozen=True, slots=True)
class WeComDepartment:
    department_id: int
    name: str
    parent_id: int | None
    order: int | None


@dataclass(frozen=True, slots=True)
class WeComContactWay:
    config_id: str
    qr_code_url: str | None


class WeComClient:
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

    def _credentials(self) -> tuple[str, int, str]:
        secret = self._settings.wecom_app_secret
        if not self._settings.wecom_corp_id or not self._settings.wecom_agent_id or not secret:
            raise WeComConfigurationError("wecom_not_configured")
        return (
            self._settings.wecom_corp_id,
            self._settings.wecom_agent_id,
            secret.get_secret_value(),
        )

    def _token_cache_key(self, corp_id: str) -> str:
        digest = hashlib.sha256(corp_id.encode("utf-8")).hexdigest()[:20]
        return f"wecom:access-token:{digest}"

    def build_oauth_authorize_url(self, *, state: str) -> str:
        corp_id, agent_id, _secret = self._credentials()
        redirect_uri = self._settings.wecom_oauth_redirect_uri
        if not redirect_uri:
            raise WeComConfigurationError("wecom_oauth_not_configured")
        if not state.isascii() or not state.isalnum() or not 1 <= len(state) <= 128:
            raise WeComConfigurationError("wecom_oauth_state_invalid")
        query = urlencode(
            {
                "appid": corp_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "snsapi_base",
                "state": state,
                "agentid": agent_id,
            }
        )
        return f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect"

    async def access_token(self, *, force_refresh: bool = False) -> str:
        corp_id, _agent_id, secret = self._credentials()
        cache_key = self._token_cache_key(corp_id)
        if self._redis is not None and not force_refresh:
            cached = await self._redis.get(cache_key)
            if cached:
                return str(cached)

        payload = await self._request_json(
            "GET",
            "/cgi-bin/gettoken",
            params={"corpid": corp_id, "corpsecret": secret},
        )
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not isinstance(token, str) or not token:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        ttl = max(60, int(expires_in or 7200) - 300)
        if self._redis is not None:
            await self._redis.set(cache_key, token, ex=ttl)
        return token

    async def probe(self) -> WeComProbeResult:
        _corp_id, agent_id, _secret = self._credentials()
        token = await self.access_token(force_refresh=True)
        payload = await self._request_json(
            "GET",
            "/cgi-bin/agent/get",
            params={"access_token": token, "agentid": agent_id},
        )
        agent_name = payload.get("name")
        return WeComProbeResult(
            corp_name=None,
            agent_name=agent_name if isinstance(agent_name, str) else None,
        )

    async def send_text(self, *, user_id: str, content: str) -> WeComMessageResult:
        _corp_id, agent_id, _secret = self._credentials()
        token = await self.access_token()
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

    async def send_text_card(
        self,
        *,
        user_id: str,
        title: str,
        description: str,
        url: str,
        button_text: str = "查看报告",
    ) -> WeComMessageResult:
        _corp_id, agent_id, _secret = self._credentials()
        token = await self.access_token()
        payload = await self._request_json(
            "POST",
            "/cgi-bin/message/send",
            params={"access_token": token},
            json=build_wecom_text_card_payload(
                user_id=user_id,
                agent_id=agent_id,
                title=title,
                description=description,
                url=url,
                button_text=button_text,
            ),
        )
        return parse_wecom_message_result(payload)

    async def get_user_identity(self, *, code: str) -> WeComUserIdentity:
        token = await self.access_token()
        payload = await self._request_json(
            "GET",
            "/cgi-bin/user/getuserinfo",
            params={"access_token": token, "code": code},
        )
        user_id = payload.get("UserId")
        if not isinstance(user_id, str) or not user_id:
            raise WeComProviderError("WECOM_INTERNAL_MEMBER_REQUIRED")
        device_id = payload.get("DeviceId")
        return WeComUserIdentity(
            user_id=user_id,
            device_id=device_id if isinstance(device_id, str) and device_id else None,
        )

    async def get_member(self, *, user_id: str) -> WeComMember:
        token = await self.access_token()
        payload = await self._request_json(
            "GET",
            "/cgi-bin/user/get",
            params={"access_token": token, "userid": user_id},
        )
        returned_id = payload.get("userid")
        if not isinstance(returned_id, str) or not returned_id:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        departments = payload.get("department")
        if not isinstance(departments, list) or not all(
            isinstance(item, int) for item in departments
        ):
            departments = []
        name = payload.get("name")
        position = payload.get("position")
        avatar = payload.get("avatar")
        status = payload.get("status")
        return WeComMember(
            user_id=returned_id,
            name=name if isinstance(name, str) and name else None,
            departments=tuple(departments),
            position=position if isinstance(position, str) and position else None,
            avatar_url=avatar if isinstance(avatar, str) and avatar else None,
            status=status if isinstance(status, int) else None,
        )

    async def list_departments(
        self, *, department_id: int | None = None
    ) -> tuple[WeComDepartment, ...]:
        token = await self.access_token()
        params: dict[str, object] = {"access_token": token}
        if department_id is not None:
            params["id"] = department_id
        payload = await self._request_json(
            "GET",
            "/cgi-bin/department/list",
            params=params,
        )
        raw_departments = payload.get("department")
        if not isinstance(raw_departments, list):
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        result: list[WeComDepartment] = []
        for value in raw_departments:
            if not isinstance(value, dict):
                raise WeComProviderError("WECOM_INVALID_RESPONSE")
            item_id = value.get("id")
            name = value.get("name")
            if not isinstance(item_id, int) or not isinstance(name, str) or not name:
                raise WeComProviderError("WECOM_INVALID_RESPONSE")
            parent_id = value.get("parentid")
            order = value.get("order")
            result.append(
                WeComDepartment(
                    department_id=item_id,
                    name=name,
                    parent_id=parent_id if isinstance(parent_id, int) else None,
                    order=order if isinstance(order, int) else None,
                )
            )
        return tuple(result)

    async def add_contact_way(
        self,
        *,
        user_ids: tuple[str, ...],
        state: str | None = None,
        remark: str | None = None,
        skip_verify: bool = True,
    ) -> WeComContactWay:
        if not user_ids:
            raise ValueError("at least one WeCom member is required")
        if state is not None and len(state) > 30:
            raise ValueError("WeCom contact-way state is too long")
        token = await self.access_token()
        body: dict[str, object] = {
            "type": 1,
            "scene": 2,
            "user": list(user_ids),
            "skip_verify": skip_verify,
        }
        if state:
            body["state"] = state
        if remark:
            body["remark"] = remark[:30]
        payload = await self._request_json(
            "POST",
            "/cgi-bin/externalcontact/add_contact_way",
            params={"access_token": token},
            json=body,
        )
        config_id = payload.get("config_id")
        qr_code = payload.get("qr_code")
        if not isinstance(config_id, str) or not config_id:
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        return WeComContactWay(
            config_id=config_id,
            qr_code_url=qr_code if isinstance(qr_code, str) and qr_code else None,
        )

    async def get_external_contact(self, *, external_user_id: str) -> dict[str, object]:
        token = await self.access_token()
        return await self._request_json(
            "GET",
            "/cgi-bin/externalcontact/get",
            params={"access_token": token, "external_userid": external_user_id},
        )

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
        if not isinstance(provider_code, int):
            raise WeComProviderError("WECOM_INVALID_RESPONSE")
        if provider_code != 0:
            raise WeComProviderError(
                "WECOM_PROVIDER_REJECTED",
                provider_code=provider_code,
            )
        return payload


__all__ = [
    "WeComClient",
    "WeComConfigurationError",
    "WeComContactWay",
    "WeComDepartment",
    "WeComMember",
    "WeComMessageResult",
    "WeComProbeResult",
    "WeComProviderError",
    "WeComUserIdentity",
    "build_wecom_text_card_payload",
]
