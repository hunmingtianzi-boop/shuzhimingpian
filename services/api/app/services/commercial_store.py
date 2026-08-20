from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.commercial_schemas import (
    CommercialEntitlementRecord,
    CommercialFeatureRecord,
    CommercialLimitRecord,
    CommercialPlanRecord,
    UpdateCommercialEntitlementRequest,
)
from app.api.errors import ApiError
from app.commercial.entitlements import (
    FEATURE_CATALOG,
    LIMIT_CATALOG,
    PLAN_CATALOG,
    commercial_settings_payload,
    feature_definition,
    limit_definition,
    resolve_commercial_entitlements,
)
from app.db.models import Company, MembershipRole
from app.db.session import set_rls_context
from app.services.audit import append_audit


@dataclass(frozen=True, slots=True)
class CommercialActor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    role: str


class CommercialStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def get_entitlements(
        self,
        *,
        actor: CommercialActor,
        company_id: uuid.UUID | None = None,
    ) -> CommercialEntitlementRecord:
        target_company_id = company_id or actor.company_id
        if (
            target_company_id != actor.company_id
            and actor.role != MembershipRole.PLATFORM_ADMIN.value
        ):
            raise ApiError(403, "FORBIDDEN", "无权查看其他企业的商业授权")
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, actor)
            company = await session.scalar(
                select(Company).where(
                    Company.id == target_company_id,
                    Company.deleted_at.is_(None),
                )
            )
            if company is None:
                raise ApiError(404, "ENTERPRISE_NOT_FOUND", "企业不存在")
            return _record(company)

    async def update_entitlements(
        self,
        *,
        actor: CommercialActor,
        company_id: uuid.UUID,
        body: UpdateCommercialEntitlementRequest,
        trace_id: str | None,
    ) -> CommercialEntitlementRecord:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可调整商业授权")
        unknown_features = sorted(
            feature_id
            for feature_id in body.feature_overrides
            if feature_definition(feature_id) is None
        )
        if unknown_features:
            raise ApiError(
                422,
                "UNKNOWN_COMMERCIAL_FEATURE",
                "功能开关包含未知能力",
                details={"feature_ids": unknown_features},
            )
        locked_features = sorted(
            feature_id
            for feature_id in body.feature_overrides
            if not feature_definition(feature_id).overrideable  # type: ignore[union-attr]
        )
        if locked_features:
            raise ApiError(
                422,
                "REQUIRED_FEATURE_OVERRIDE_FORBIDDEN",
                "系统必需能力不能覆盖",
                details={"feature_ids": locked_features},
            )
        unknown_limits = sorted(
            limit_id for limit_id in body.limit_overrides if limit_definition(limit_id) is None
        )
        if unknown_limits:
            raise ApiError(
                422,
                "UNKNOWN_COMMERCIAL_LIMIT",
                "套餐额度包含未知指标",
                details={"limit_ids": unknown_limits},
            )

        async with self._sessions() as session, session.begin():
            await self._set_scope(session, actor)
            company = await session.scalar(
                select(Company)
                .where(Company.id == company_id, Company.deleted_at.is_(None))
                .with_for_update()
            )
            if company is None:
                raise ApiError(404, "ENTERPRISE_NOT_FOUND", "企业不存在")
            if company.version != body.expected_version:
                raise ApiError(409, "VERSION_CONFLICT", "企业授权已变化，请刷新后重试")

            settings = dict(company.settings or {})
            previous = resolve_commercial_entitlements(settings)
            settings["commercial_entitlements"] = commercial_settings_payload(
                plan_code=body.plan_code,
                billing_cycle=body.billing_cycle,
                contract_price_cny=body.contract_price_cny,
                feature_overrides=body.feature_overrides,
                limit_overrides=body.limit_overrides,
            )
            company.settings = settings
            company.version += 1
            current = resolve_commercial_entitlements(settings)
            await append_audit(
                session,
                tenant_id=company.tenant_id,
                company_id=company.id,
                actor_user_id=actor.user_id,
                action="platform.enterprise.entitlements.update",
                resource_type="company_commercial_entitlements",
                resource_id=company.id,
                trace_id=trace_id,
                event_data={
                    "previous_plan_code": previous.plan_code,
                    "plan_code": current.plan_code,
                    "billing_cycle": current.billing_cycle,
                    "feature_override_count": len(current.feature_overrides),
                    "limit_override_count": len(current.limit_overrides),
                    "company_version": company.version,
                },
            )
            return _record(company)

    @staticmethod
    async def _set_scope(session: AsyncSession, actor: CommercialActor) -> None:
        await set_rls_context(
            session,
            tenant_id=actor.tenant_id,
            company_id=actor.company_id,
            actor_user_id=actor.user_id,
            actor_session_id=actor.session_id,
        )


def _record(company: Company) -> CommercialEntitlementRecord:
    state = resolve_commercial_entitlements(company.settings)
    return CommercialEntitlementRecord(
        company_id=company.id,
        company_version=company.version,
        plan_code=state.plan_code,
        billing_cycle=state.billing_cycle,
        contract_price_cny=state.contract_price_cny,
        feature_overrides=state.feature_overrides,
        features=state.features,
        limit_overrides=state.limit_overrides,
        limits=state.limits,
        plans=[
            CommercialPlanRecord(
                code=plan.code,
                name=plan.name,
                description=plan.description,
            )
            for plan in PLAN_CATALOG
        ],
        feature_catalog=[
            CommercialFeatureRecord(
                id=feature.id,
                name=feature.name,
                group=feature.group,
                description=feature.description,
                minimum_plan=feature.minimum_plan,
                overrideable=feature.overrideable,
            )
            for feature in FEATURE_CATALOG
        ],
        limit_catalog=[
            CommercialLimitRecord(
                id=limit.id,
                name=limit.name,
                group=limit.group,
                description=limit.description,
                unit=limit.unit,
                plan_defaults=dict(limit.plan_defaults),
            )
            for limit in LIMIT_CATALOG
        ],
    )


__all__ = ["CommercialActor", "CommercialStore"]
