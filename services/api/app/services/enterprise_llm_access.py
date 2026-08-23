from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import httpx
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import (
    CompanyLLMConfiguration,
    LifecycleStatus,
    Membership,
    MembershipRole,
    Notification,
    PlatformLLMProfile,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit
from app.services.platform_llm_profiles import (
    PlatformLLMProbeResult,
    database_chat_config,
    key_hint,
    probe_openai_models,
)


@dataclass(frozen=True, slots=True)
class EnterpriseLLMActor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class EnterpriseLLMUpdate:
    platform_profile_id: uuid.UUID
    mode: Literal["platform_managed", "byok"]
    daily_budget_cny: float
    expected_version: int
    api_key: str | None = field(default=None, repr=False)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class EnterpriseLLMView:
    platform_profile_id: uuid.UUID
    profile_name: str
    provider: str
    base_url: str
    model: str
    mode: Literal["platform_managed", "byok"]
    daily_budget_cny: float
    platform_budget_ceiling_cny: float
    enabled: bool
    key_configured: bool
    key_hint: str | None
    version: int
    configured: bool
    delegated: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EnterpriseLLMProfileOption:
    id: uuid.UUID
    name: str
    provider: str
    base_url: str
    model: str
    daily_budget_ceiling_cny: float
    is_default: bool


class EnterpriseLLMAccessService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._http = http_client
        self._cipher = PiiCipher.from_settings(settings)

    async def options(self, *, actor: EnterpriseLLMActor) -> list[EnterpriseLLMProfileOption]:
        self._require_company_admin(actor)
        async with self._sessions() as session, session.begin():
            await self._scope(session, actor)
            rows = (
                await session.scalars(
                    select(PlatformLLMProfile)
                    .where(PlatformLLMProfile.enabled.is_(True))
                    .order_by(
                        PlatformLLMProfile.is_active.desc(),
                        PlatformLLMProfile.name,
                    )
                )
            ).all()
        return [self._option(row) for row in rows]

    async def get(
        self,
        *,
        actor: EnterpriseLLMActor,
        target_tenant_id: uuid.UUID | None = None,
        target_company_id: uuid.UUID | None = None,
    ) -> EnterpriseLLMView:
        delegated = target_tenant_id is not None or target_company_id is not None
        if delegated:
            if actor.role != MembershipRole.PLATFORM_ADMIN.value:
                raise ApiError(403, "FORBIDDEN", "仅平台管理员可查看企业模型接入")
            if target_tenant_id is None or target_company_id is None:
                raise ApiError(422, "TARGET_SCOPE_REQUIRED", "企业范围不完整")
        else:
            self._require_company_admin(actor)
            target_tenant_id = actor.tenant_id
            target_company_id = actor.company_id

        assert target_tenant_id is not None and target_company_id is not None
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=target_tenant_id,
                company_id=target_company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            row = await session.scalar(
                select(CompanyLLMConfiguration).where(
                    CompanyLLMConfiguration.tenant_id == target_tenant_id,
                    CompanyLLMConfiguration.company_id == target_company_id,
                )
            )
            if row is None:
                profile = await self._default_profile(session)
                return self._view_default(profile)
            profile = await self._profile(session, row.platform_profile_id)
            return self._view(row, profile)

    async def update(
        self,
        *,
        actor: EnterpriseLLMActor,
        body: EnterpriseLLMUpdate,
        trace_id: str | None,
        target_tenant_id: uuid.UUID | None = None,
        target_company_id: uuid.UUID | None = None,
        delegated_reason: str | None = None,
    ) -> EnterpriseLLMView:
        delegated = target_company_id is not None or target_tenant_id is not None
        if delegated:
            if actor.role != MembershipRole.PLATFORM_ADMIN.value:
                raise ApiError(403, "FORBIDDEN", "仅平台管理员可受委托配置企业模型")
            reason = (delegated_reason or "").strip()
            if len(reason) < 3 or len(reason) > 500:
                raise ApiError(422, "DELEGATION_REASON_REQUIRED", "受委托配置必须填写原因")
            if target_tenant_id is None or target_company_id is None:
                raise ApiError(422, "TARGET_SCOPE_REQUIRED", "企业范围不完整")
        else:
            self._require_company_admin(actor)
            target_tenant_id = actor.tenant_id
            target_company_id = actor.company_id
            reason = None

        assert target_tenant_id is not None and target_company_id is not None
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=target_tenant_id,
                company_id=target_company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            profile = await self._profile(session, body.platform_profile_id)
            budget = Decimal(str(body.daily_budget_cny))
            if budget < 0 or budget > profile.daily_budget_cny:
                raise ApiError(
                    422,
                    "LLM_BUDGET_EXCEEDS_PLATFORM_LIMIT",
                    "企业每日预算不能超过平台配置上限",
                    details={"maximum": float(profile.daily_budget_cny)},
                )
            row = await session.scalar(
                select(CompanyLLMConfiguration)
                .where(
                    CompanyLLMConfiguration.tenant_id == target_tenant_id,
                    CompanyLLMConfiguration.company_id == target_company_id,
                )
                .with_for_update()
            )
            if row is None:
                if body.expected_version != 0:
                    raise ApiError(409, "LLM_ACCESS_VERSION_CONFLICT", "模型接入设置已变化，请刷新")
                row = CompanyLLMConfiguration(
                    id=uuid.uuid4(),
                    tenant_id=target_tenant_id,
                    company_id=target_company_id,
                    platform_profile_id=profile.id,
                    version=1,
                )
                session.add(row)
            else:
                if row.version != body.expected_version:
                    raise ApiError(409, "LLM_ACCESS_VERSION_CONFLICT", "模型接入设置已变化，请刷新")
                row.version += 1

            secret = (body.api_key or "").strip()
            if body.mode == "byok":
                if secret:
                    row.api_key_ciphertext = self._cipher.encrypt(secret)
                    row.api_key_key_ref = self._cipher.key_ref
                    row.api_key_hint = key_hint(secret)
                elif row.mode != "byok" or row.api_key_ciphertext is None:
                    raise ApiError(422, "LLM_API_KEY_REQUIRED", "使用企业 API Key 时必须先填写密钥")
            else:
                row.api_key_ciphertext = None
                row.api_key_key_ref = None
                row.api_key_hint = None
            row.platform_profile_id = profile.id
            row.mode = body.mode
            row.daily_budget_cny = budget
            row.enabled = body.enabled
            row.updated_by = actor.user_id
            row.delegated_by = actor.user_id if delegated else None
            row.delegated_reason = reason
            await session.flush()
            await append_audit(
                session,
                tenant_id=target_tenant_id,
                company_id=target_company_id,
                actor_user_id=actor.user_id,
                action=(
                    "enterprise.llm_access.delegated_update"
                    if delegated
                    else "enterprise.llm_access.update"
                ),
                resource_type="company_llm_configuration",
                resource_id=row.id,
                trace_id=trace_id,
                event_data={
                    "platform_profile_id": str(profile.id),
                    "mode": body.mode,
                    "daily_budget_cny": float(budget),
                    "key_changed": bool(secret),
                    "delegated": delegated,
                    "delegated_reason": reason,
                    "version": row.version,
                },
            )
            if delegated:
                await self._notify_admins(
                    session,
                    tenant_id=target_tenant_id,
                    company_id=target_company_id,
                    resource_id=row.id,
                )
            await session.refresh(row)
            return self._view(row, profile)

    async def test(
        self,
        *,
        actor: EnterpriseLLMActor,
        api_key_override: str | None = None,
    ) -> PlatformLLMProbeResult:
        self._require_company_admin(actor)
        async with self._sessions() as session, session.begin():
            await self._scope(session, actor)
            row = await session.scalar(
                select(CompanyLLMConfiguration).where(
                    CompanyLLMConfiguration.tenant_id == actor.tenant_id,
                    CompanyLLMConfiguration.company_id == actor.company_id,
                )
            )
            if row is None:
                profile = await self._default_profile(session)
                key = None
            else:
                profile = await self._profile(session, row.platform_profile_id)
                key = None
                if row.mode == "byok":
                    override = (api_key_override or "").strip()
                    if override:
                        key = SecretStr(override)
                    elif row.api_key_ciphertext is not None:
                        key = SecretStr(self._cipher.decrypt(row.api_key_ciphertext))
            config = database_chat_config(profile, settings=self._settings, api_key_override=key)
        return await probe_openai_models(self._http, config)

    @staticmethod
    def _require_company_admin(actor: EnterpriseLLMActor) -> None:
        if actor.role not in {
            MembershipRole.COMPANY_ADMIN.value,
            MembershipRole.PLATFORM_ADMIN.value,
        }:
            raise ApiError(403, "FORBIDDEN", "仅企业管理员可管理模型接入")

    @staticmethod
    async def _scope(session: AsyncSession, actor: EnterpriseLLMActor) -> None:
        await set_rls_context(
            session,
            tenant_id=actor.tenant_id,
            company_id=actor.company_id,
            actor_user_id=actor.user_id,
            actor_session_id=actor.session_id,
        )

    @staticmethod
    async def _profile(session: AsyncSession, profile_id: uuid.UUID) -> PlatformLLMProfile:
        profile = await session.scalar(
            select(PlatformLLMProfile).where(PlatformLLMProfile.id == profile_id)
        )
        if profile is None or not profile.enabled:
            raise ApiError(422, "LLM_PROFILE_NOT_ALLOWED", "所选模型不在平台可用白名单中")
        return profile

    @staticmethod
    async def _default_profile(session: AsyncSession) -> PlatformLLMProfile:
        profile = await session.scalar(
            select(PlatformLLMProfile).where(
                PlatformLLMProfile.is_active.is_(True),
                PlatformLLMProfile.enabled.is_(True),
            )
        )
        if profile is None:
            raise ApiError(503, "LLM_RUNTIME_UNAVAILABLE", "平台尚未配置可用模型")
        return profile

    @staticmethod
    def _option(row: PlatformLLMProfile) -> EnterpriseLLMProfileOption:
        return EnterpriseLLMProfileOption(
            id=row.id,
            name=row.name,
            provider=row.provider,
            base_url=row.base_url,
            model=row.model,
            daily_budget_ceiling_cny=float(row.daily_budget_cny),
            is_default=row.is_active,
        )

    @staticmethod
    def _view_default(profile: PlatformLLMProfile) -> EnterpriseLLMView:
        return EnterpriseLLMView(
            platform_profile_id=profile.id,
            profile_name=profile.name,
            provider=profile.provider,
            base_url=profile.base_url,
            model=profile.model,
            mode="platform_managed",
            daily_budget_cny=float(profile.daily_budget_cny),
            platform_budget_ceiling_cny=float(profile.daily_budget_cny),
            enabled=True,
            key_configured=False,
            key_hint=None,
            version=0,
            configured=False,
            delegated=False,
            updated_at=profile.updated_at,
        )

    @staticmethod
    def _view(row: CompanyLLMConfiguration, profile: PlatformLLMProfile) -> EnterpriseLLMView:
        return EnterpriseLLMView(
            platform_profile_id=profile.id,
            profile_name=profile.name,
            provider=profile.provider,
            base_url=profile.base_url,
            model=profile.model,
            mode=row.mode,  # type: ignore[arg-type]
            daily_budget_cny=float(row.daily_budget_cny),
            platform_budget_ceiling_cny=float(profile.daily_budget_cny),
            enabled=row.enabled,
            key_configured=row.api_key_ciphertext is not None,
            key_hint=row.api_key_hint,
            version=row.version,
            configured=True,
            delegated=row.delegated_by is not None,
            updated_at=row.updated_at,
        )

    @staticmethod
    async def _notify_admins(
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        resource_id: uuid.UUID,
    ) -> None:
        admin_ids = (
            await session.scalars(
                select(Membership.user_id).where(
                    Membership.tenant_id == tenant_id,
                    Membership.company_id == company_id,
                    Membership.role == MembershipRole.COMPANY_ADMIN,
                    Membership.status == LifecycleStatus.ACTIVE,
                )
            )
        ).all()
        for user_id in admin_ids:
            session.add(
                Notification(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    company_id=company_id,
                    recipient_user_id=user_id,
                    notification_type="llm_configuration_updated",
                    title="企业模型接入设置已更新",
                    body="平台管理员已按受委托原因更新模型接入，请在 AI 设置中复核。",
                    resource_type="company_llm_configuration",
                    resource_id=resource_id,
                    created_at=datetime.now(UTC),
                )
            )


__all__ = [
    "EnterpriseLLMAccessService",
    "EnterpriseLLMActor",
    "EnterpriseLLMProfileOption",
    "EnterpriseLLMUpdate",
    "EnterpriseLLMView",
]
