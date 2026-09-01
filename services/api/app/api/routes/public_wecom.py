from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.api.errors import ApiError
from app.api.wecom_schemas import (
    WeComPublicJSSDKConfig,
    WeComPublicJSSDKConfigEnvelope,
)
from app.db.session import resolve_public_card_scope
from app.integrations.wecom import WeComConfigurationError, WeComProviderError
from app.integrations.wecom_suite import WeComSuiteClient
from app.services.wecom_js_sdk import (
    build_wecom_js_sdk_signatures,
    normalize_public_card_js_sdk_url,
)
from app.services.wecom_suite_store import WeComSuiteStore

router = APIRouter(tags=["Public WeCom"])


@router.get(
    "/public/cards/{slug}/wecom-js-sdk",
    response_model=WeComPublicJSSDKConfigEnvelope,
    operation_id="getPublicCardWeComJSSDKConfig",
)
async def get_public_card_wecom_js_sdk_config(
    slug: str,
    request: Request,
    response: Response,
    url: Annotated[str, Query(min_length=1, max_length=2_048)],
) -> WeComPublicJSSDKConfigEnvelope:
    settings = request.app.state.settings
    normalized_url = normalize_public_card_js_sdk_url(
        value=url,
        slug=slug,
        settings=settings,
    )
    async with request.app.state.session_factory() as session, session.begin():
        scope = await resolve_public_card_scope(session, slug)
    if scope is None:
        raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")

    authorization = await WeComSuiteStore(
        request.app.state.session_factory,
        settings,
    ).get_authorization_for_scope(
        tenant_id=scope.tenant_id,
        company_id=scope.company_id,
    )
    if authorization.agent_id is None:
        raise ApiError(409, "WECOM_AGENT_NOT_CONFIGURED", "该企业的企微应用尚未完成授权")

    client = WeComSuiteClient(
        settings=settings,
        http_client=getattr(
            request.app.state,
            "wecom_http_client",
            request.app.state.http_client,
        ),
        redis=getattr(request.app.state, "redis", None),
    )
    try:
        config_ticket = await client.jsapi_ticket(
            auth_corpid=authorization.auth_corpid,
            permanent_code=authorization.permanent_code,
            ticket_type="corp",
        )
        agent_config_ticket = await client.jsapi_ticket(
            auth_corpid=authorization.auth_corpid,
            permanent_code=authorization.permanent_code,
            ticket_type="agent_config",
        )
    except WeComConfigurationError as exc:
        raise ApiError(409, "WECOM_JS_SDK_NOT_READY", "企业微信签名服务尚未配置") from exc
    except WeComProviderError as exc:
        details = {"provider_code": exc.provider_code} if exc.provider_code is not None else None
        message = (
            "企微服务商 IP 白名单尚未包含当前服务器"
            if exc.provider_code == 60020
            else "企业微信签名服务暂时不可用"
        )
        raise ApiError(502, exc.code, message, details=details) from exc

    signatures = build_wecom_js_sdk_signatures(
        url=normalized_url,
        config_ticket=config_ticket,
        agent_config_ticket=agent_config_ticket,
    )
    response.headers["Cache-Control"] = "no-store"
    return WeComPublicJSSDKConfigEnvelope(
        data=WeComPublicJSSDKConfig(
            corp_id=authorization.auth_corpid,
            agent_id=authorization.agent_id,
            url=signatures.url,
            timestamp=signatures.timestamp,
            nonce_str=signatures.nonce_str,
            config_signature=signatures.config_signature,
            agent_config_signature=signatures.agent_config_signature,
        )
    )


__all__ = ["router"]
