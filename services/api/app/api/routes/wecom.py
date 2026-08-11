from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.wecom_schemas import (
    WeComDepartmentList,
    WeComDepartmentListEnvelope,
    WeComDepartmentRecord,
    WeComIntegrationStatus,
    WeComIntegrationStatusEnvelope,
    WeComTestMessageEnvelope,
    WeComTestMessageRecord,
    WeComTestMessageRequest,
)
from app.core.tokens import StaffPrincipal
from app.integrations.wecom import (
    WeComClient,
    WeComConfigurationError,
    WeComProviderError,
)

router = APIRouter(prefix="/platform/integrations/wecom", tags=["WeCom Integration"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _require_platform_admin(principal: StaffPrincipal) -> None:
    if str(getattr(principal.role, "value", principal.role)) != "platform_admin":
        raise ApiError(403, "FORBIDDEN", "仅平台管理员可配置企业微信")


def _client(request: Request) -> WeComClient:
    return WeComClient(
        settings=request.app.state.settings,
        http_client=getattr(
            request.app.state, "wecom_http_client", request.app.state.http_client
        ),
        redis=getattr(request.app.state, "redis", None),
    )


def _corp_hint(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


def _provider_error(exc: WeComProviderError) -> ApiError:
    details: dict[str, object] = {}
    if exc.provider_code is not None:
        details["provider_code"] = exc.provider_code
    return ApiError(
        502,
        exc.code,
        "企业微信暂时无法完成连接，请核对应用权限和安全配置",
        details=details,
    )


@router.get(
    "/status",
    response_model=WeComIntegrationStatusEnvelope,
    operation_id="getWeComIntegrationStatus",
)
async def get_wecom_integration_status(
    request: Request,
    principal: StaffDependency,
    probe: Annotated[bool, Query()] = False,
) -> WeComIntegrationStatusEnvelope:
    _require_platform_admin(principal)
    settings = request.app.state.settings
    configured = bool(
        settings.wecom_corp_id and settings.wecom_agent_id and settings.wecom_app_secret
    )
    status = WeComIntegrationStatus(
        configured=configured,
        callback_configured=bool(
            settings.wecom_callback_token and settings.wecom_callback_encoding_aes_key
        ),
        oauth_configured=bool(settings.wecom_oauth_redirect_uri),
        identity_scope_configured=bool(
            settings.wecom_tenant_id and settings.wecom_company_id
        ),
        corp_id_hint=_corp_hint(settings.wecom_corp_id),
        agent_id=settings.wecom_agent_id,
    )
    if not probe or not configured:
        return WeComIntegrationStatusEnvelope(data=status)
    try:
        result = await _client(request).probe()
    except WeComConfigurationError:
        status.configured = False
        status.reachable = False
        status.error_code = "WECOM_NOT_CONFIGURED"
    except WeComProviderError as exc:
        status.reachable = False
        status.error_code = exc.code
    else:
        status.reachable = True
        status.agent_name = result.agent_name
    return WeComIntegrationStatusEnvelope(data=status)


@router.post(
    "/test-message",
    response_model=WeComTestMessageEnvelope,
    operation_id="sendWeComTestMessage",
)
async def send_wecom_test_message(
    payload: WeComTestMessageRequest,
    request: Request,
    principal: StaffDependency,
) -> WeComTestMessageEnvelope:
    _require_platform_admin(principal)
    try:
        result = await _client(request).send_text(
            user_id=payload.user_id,
            content=payload.content,
        )
    except WeComConfigurationError as exc:
        raise ApiError(409, "WECOM_NOT_CONFIGURED", "企业微信尚未完成配置") from exc
    except WeComProviderError as exc:
        raise _provider_error(exc) from exc
    return WeComTestMessageEnvelope(
        data=WeComTestMessageRecord(delivered=True, message_id=result.message_id)
    )


@router.get(
    "/departments",
    response_model=WeComDepartmentListEnvelope,
    operation_id="listWeComDepartments",
)
async def list_wecom_departments(
    request: Request,
    principal: StaffDependency,
    department_id: Annotated[int | None, Query(ge=1)] = None,
) -> WeComDepartmentListEnvelope:
    _require_platform_admin(principal)
    try:
        departments = await _client(request).list_departments(
            department_id=department_id
        )
    except WeComConfigurationError as exc:
        raise ApiError(409, "WECOM_NOT_CONFIGURED", "企业微信尚未完成配置") from exc
    except WeComProviderError as exc:
        raise _provider_error(exc) from exc
    return WeComDepartmentListEnvelope(
        data=WeComDepartmentList(
            items=tuple(
                WeComDepartmentRecord(
                    id=item.department_id,
                    name=item.name,
                    parent_id=item.parent_id,
                    order=item.order,
                )
                for item in departments
            )
        )
    )


__all__ = ["router"]
