from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.admin_schemas import EnterpriseLlmAccess, EnterpriseLlmAccessEnvelope
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.platform_schemas import (
    ActivatePlatformLlmProfileRequest,
    CreatePlatformLlmProfileRequest,
    DelegateEnterpriseLlmAccessRequest,
    PlatformLlmConnectionTestEnvelope,
    PlatformLlmConnectionTestRecord,
    PlatformLlmProfileEnvelope,
    PlatformLlmProfileListEnvelope,
    PlatformLlmProfileRecord,
    TestPlatformLlmProfileRequest,
    UpdatePlatformLlmProfileRequest,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.db.models import Company, MembershipRole
from app.db.session import set_rls_context
from app.services.enterprise_llm_access import (
    EnterpriseLLMAccessService,
    EnterpriseLLMActor,
    EnterpriseLLMUpdate,
)
from app.services.platform_llm_profiles import (
    ActivateProfileInput,
    CreateProfileInput,
    PlatformLLMActor,
    PlatformLLMProfileService,
    PlatformLLMProfileView,
    UpdateProfileInput,
)

router = APIRouter(
    prefix="/platform/settings/llm/profiles",
    tags=["Platform LLM Settings"],
)
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _service(request: Request) -> PlatformLLMProfileService:
    return PlatformLLMProfileService(
        request.app.state.session_factory,
        request.app.state.settings,
        request.app.state.http_client,
    )


def _enterprise_access_service(request: Request) -> EnterpriseLLMAccessService:
    return EnterpriseLLMAccessService(
        request.app.state.session_factory,
        request.app.state.settings,
        request.app.state.http_client,
    )


def _actor(principal: StaffPrincipal) -> PlatformLLMActor:
    role = str(getattr(principal.role, "value", principal.role))
    if role != MembershipRole.PLATFORM_ADMIN.value:
        raise ApiError(403, "FORBIDDEN", "仅平台管理员可管理 LLM 配置")
    return PlatformLLMActor(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        session_id=principal.session_id,
        role=role,
    )


def _enterprise_actor(principal: StaffPrincipal) -> EnterpriseLLMActor:
    actor = _actor(principal)
    return EnterpriseLLMActor(
        user_id=actor.user_id,
        tenant_id=actor.tenant_id,
        company_id=actor.company_id,
        session_id=actor.session_id,
        role=actor.role,
    )


@router.put(
    "/companies/{company_id}/access",
    response_model=EnterpriseLlmAccessEnvelope,
    operation_id="delegateEnterpriseLlmAccess",
)
async def delegate_enterprise_llm_access(
    company_id: uuid.UUID,
    body: DelegateEnterpriseLlmAccessRequest,
    request: Request,
    principal: StaffDependency,
) -> EnterpriseLlmAccessEnvelope:
    actor = _enterprise_actor(principal)
    async with request.app.state.session_factory() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=principal.tenant_id,
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            actor_session_id=principal.session_id,
        )
        company = await session.get(Company, company_id)
    if company is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "企业不存在")
    view = await _enterprise_access_service(request).update(
        actor=actor,
        body=EnterpriseLLMUpdate(
            platform_profile_id=body.platform_profile_id,
            mode=body.mode,
            daily_budget_cny=body.daily_budget_cny,
            expected_version=body.expected_version,
            api_key=body.api_key.get_secret_value() if body.api_key else None,
            enabled=body.enabled,
        ),
        trace_id=request_id_ctx.get(),
        target_tenant_id=company.tenant_id,
        target_company_id=company.id,
        delegated_reason=body.reason,
    )
    return EnterpriseLlmAccessEnvelope(data=EnterpriseLlmAccess(**asdict(view)))


@router.get(
    "/companies/{company_id}/access",
    response_model=EnterpriseLlmAccessEnvelope,
    operation_id="getDelegatedEnterpriseLlmAccess",
)
async def get_delegated_enterprise_llm_access(
    company_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> EnterpriseLlmAccessEnvelope:
    actor = _enterprise_actor(principal)
    async with request.app.state.session_factory() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=principal.tenant_id,
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            actor_session_id=principal.session_id,
        )
        company = await session.get(Company, company_id)
    if company is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "企业不存在")
    view = await _enterprise_access_service(request).get(
        actor=actor,
        target_tenant_id=company.tenant_id,
        target_company_id=company.id,
    )
    return EnterpriseLlmAccessEnvelope(data=EnterpriseLlmAccess(**asdict(view)))


def _record(view: PlatformLLMProfileView) -> PlatformLlmProfileRecord:
    """Map an internal view to the frozen public response allowlist."""

    return PlatformLlmProfileRecord(
        id=view.id,
        name=view.name,
        purpose=view.purpose,
        provider=view.provider,
        base_url=view.base_url,
        model=view.model,
        thinking=view.thinking,
        reasoning_effort=view.reasoning_effort,
        timeout_seconds=view.timeout_seconds,
        max_retries=view.max_retries,
        max_concurrency=view.max_concurrency,
        max_output_tokens=view.max_output_tokens,
        temperature=view.temperature,
        daily_budget_cny=view.daily_budget_cny,
        input_price_cny_per_million=view.input_price_cny_per_million,
        output_price_cny_per_million=view.output_price_cny_per_million,
        allow_general_answers=view.allow_general_answers,
        faq_fast_path_enabled=view.faq_fast_path_enabled,
        key_configured=view.key_configured,
        key_hint=view.key_hint,
        enabled=view.enabled,
        is_active=view.is_active,
        version=view.version,
        last_test_status=view.last_test_status,
        last_test_latency_ms=view.last_test_latency_ms,
        last_tested_at=view.last_tested_at,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


@router.get(
    "",
    response_model=PlatformLlmProfileListEnvelope,
    operation_id="listPlatformLlmProfiles",
)
async def list_profiles(
    request: Request,
    principal: StaffDependency,
) -> PlatformLlmProfileListEnvelope:
    actor = _actor(principal)
    records = await _service(request).list_profiles(actor=actor)
    return PlatformLlmProfileListEnvelope(data=[_record(record) for record in records])


@router.post(
    "",
    response_model=PlatformLlmProfileEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPlatformLlmProfile",
)
async def create_profile(
    body: CreatePlatformLlmProfileRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformLlmProfileEnvelope:
    actor = _actor(principal)
    record = await _service(request).create_profile(
        actor=actor,
        body=CreateProfileInput(
            name=body.name,
            purpose=body.purpose,
            provider=body.provider,
            base_url=str(body.base_url),
            api_key=body.api_key.get_secret_value(),
            model=body.model,
            thinking=body.thinking,
            reasoning_effort=body.reasoning_effort,
            timeout_seconds=body.timeout_seconds,
            max_retries=body.max_retries,
            max_concurrency=body.max_concurrency,
            max_output_tokens=body.max_output_tokens,
            temperature=body.temperature,
            daily_budget_cny=body.daily_budget_cny,
            input_price_cny_per_million=body.input_price_cny_per_million,
            output_price_cny_per_million=body.output_price_cny_per_million,
            allow_general_answers=body.allow_general_answers,
            faq_fast_path_enabled=body.faq_fast_path_enabled,
            enabled=body.enabled,
        ),
        trace_id=request_id_ctx.get(),
    )
    return PlatformLlmProfileEnvelope(data=_record(record))


@router.put(
    "/{profile_id}",
    response_model=PlatformLlmProfileEnvelope,
    operation_id="updatePlatformLlmProfile",
)
async def update_profile(
    profile_id: uuid.UUID,
    body: UpdatePlatformLlmProfileRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformLlmProfileEnvelope:
    actor = _actor(principal)
    service = _service(request)
    existing = await service.get_profile(actor=actor, profile_id=profile_id)
    supplied = body.model_fields_set

    def merged(field_name: str) -> object:
        if field_name in supplied:
            value = getattr(body, field_name)
            if value is not None or field_name == "reasoning_effort":
                return value
        return getattr(existing, field_name)

    base_url = merged("base_url")
    api_key = body.api_key.get_secret_value() if "api_key" in supplied and body.api_key else None
    record = await service.update_profile(
        actor=actor,
        profile_id=profile_id,
        body=UpdateProfileInput(
            expected_version=body.expected_version,
            name=str(merged("name")),
            purpose=existing.purpose,
            provider=str(merged("provider")),
            base_url=str(base_url),
            api_key=api_key,
            model=str(merged("model")),
            thinking=merged("thinking"),  # type: ignore[arg-type]
            reasoning_effort=merged("reasoning_effort"),  # type: ignore[arg-type]
            timeout_seconds=float(merged("timeout_seconds")),
            max_retries=int(merged("max_retries")),
            max_concurrency=int(merged("max_concurrency")),
            max_output_tokens=int(merged("max_output_tokens")),
            temperature=float(merged("temperature")),
            daily_budget_cny=float(merged("daily_budget_cny")),
            input_price_cny_per_million=float(merged("input_price_cny_per_million")),
            output_price_cny_per_million=float(merged("output_price_cny_per_million")),
            allow_general_answers=bool(merged("allow_general_answers")),
            faq_fast_path_enabled=bool(merged("faq_fast_path_enabled")),
            enabled=bool(merged("enabled")),
        ),
        trace_id=request_id_ctx.get(),
    )
    return PlatformLlmProfileEnvelope(data=_record(record))


@router.post(
    "/{profile_id}/test",
    response_model=PlatformLlmConnectionTestEnvelope,
    operation_id="testPlatformLlmProfile",
)
async def test_profile(
    profile_id: uuid.UUID,
    body: TestPlatformLlmProfileRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformLlmConnectionTestEnvelope:
    actor = _actor(principal)
    result = await _service(request).test_profile_connection(
        actor=actor,
        profile_id=profile_id,
        api_key_override=body.api_key,
        trace_id=request_id_ctx.get(),
    )
    return PlatformLlmConnectionTestEnvelope(
        data=PlatformLlmConnectionTestRecord(
            status="succeeded" if result.ok else "failed",
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            error_code=result.error_code,
        )
    )


@router.post(
    "/{profile_id}/activate",
    response_model=PlatformLlmProfileEnvelope,
    operation_id="activatePlatformLlmProfile",
)
async def activate_profile(
    profile_id: uuid.UUID,
    body: ActivatePlatformLlmProfileRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformLlmProfileEnvelope:
    actor = _actor(principal)
    record = await _service(request).activate_profile(
        actor=actor,
        profile_id=profile_id,
        body=ActivateProfileInput(
            expected_version=body.expected_version,
            expected_active_profile_id=body.expected_active_profile_id,
        ),
        trace_id=request_id_ctx.get(),
    )
    return PlatformLlmProfileEnvelope(data=_record(record))


__all__ = ["router"]
