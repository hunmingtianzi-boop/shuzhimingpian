from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.db.models import AssociationCompanyMembership, Company, MembershipRole
from app.db.session import set_rls_context
from app.services.audit import append_audit


@dataclass(frozen=True, slots=True)
class PlatformAssociationActor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class AssociationSummaryView:
    company_id: uuid.UUID
    legal_name: str
    short_name: str | None
    business_tenant_key: str
    member_count: int
    allocated_seats: int


@dataclass(frozen=True, slots=True)
class AssociationMemberView:
    id: uuid.UUID
    association_company_id: uuid.UUID
    company_id: uuid.UUID
    legal_name: str
    short_name: str | None
    business_tenant_key: str
    member_tier: str | None
    allocated_seats: int
    benefits: dict[str, object]
    version: int
    updated_at: datetime


class PlatformAssociationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def list_associations(
        self, *, actor: PlatformAssociationActor
    ) -> list[AssociationSummaryView]:
        self._require_platform(actor)
        async with self._sessions() as session, session.begin():
            await self._scope(session, actor)
            rows = (
                await session.execute(
                    select(
                        Company,
                        func.count(AssociationCompanyMembership.id),
                        func.coalesce(func.sum(AssociationCompanyMembership.allocated_seats), 0),
                    )
                    .outerjoin(
                        AssociationCompanyMembership,
                        AssociationCompanyMembership.association_company_id == Company.id,
                    )
                    .where(Company.subject_type == "association", Company.deleted_at.is_(None))
                    .group_by(Company.id)
                    .order_by(Company.name, Company.id)
                )
            ).all()
        return [
            AssociationSummaryView(
                company_id=company.id,
                legal_name=company.name,
                short_name=company.short_name,
                business_tenant_key=company.business_tenant_key,
                member_count=int(member_count),
                allocated_seats=int(allocated_seats),
            )
            for company, member_count, allocated_seats in rows
        ]

    async def list_members(
        self,
        *,
        actor: PlatformAssociationActor,
        association_company_id: uuid.UUID,
    ) -> list[AssociationMemberView]:
        self._require_platform(actor)
        async with self._sessions() as session, session.begin():
            await self._scope(session, actor)
            await self._association(session, association_company_id)
            rows = (
                await session.execute(
                    select(AssociationCompanyMembership, Company)
                    .join(Company, Company.id == AssociationCompanyMembership.member_company_id)
                    .where(
                        AssociationCompanyMembership.association_company_id
                        == association_company_id
                    )
                    .order_by(Company.name, Company.id)
                )
            ).all()
        return [self._view(membership, company) for membership, company in rows]

    async def upsert_member(
        self,
        *,
        actor: PlatformAssociationActor,
        association_company_id: uuid.UUID,
        member_company_id: uuid.UUID,
        expected_version: int,
        member_tier: str | None,
        allocated_seats: int,
        benefits: dict[str, object],
        trace_id: str | None,
    ) -> AssociationMemberView:
        self._require_platform(actor)
        normalized_tier = (member_tier or "").strip() or None
        if normalized_tier is not None and len(normalized_tier) > 80:
            raise ApiError(422, "ASSOCIATION_MEMBER_TIER_INVALID", "会员等级不能超过 80 字")
        if len(benefits) > 50:
            raise ApiError(422, "ASSOCIATION_BENEFITS_INVALID", "权益字段过多")
        async with self._sessions() as session, session.begin():
            await self._scope(session, actor)
            association = await self._association(session, association_company_id)
            member = await session.get(Company, member_company_id)
            if member is None or member.deleted_at is not None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "成员企业不存在")
            if member.subject_type == "association":
                raise ApiError(422, "ASSOCIATION_NESTING_NOT_SUPPORTED", "当前阶段不支持协会嵌套")
            row = await session.scalar(
                select(AssociationCompanyMembership)
                .where(
                    AssociationCompanyMembership.association_company_id
                    == association_company_id,
                    AssociationCompanyMembership.member_company_id == member_company_id,
                )
                .with_for_update()
            )
            if row is None:
                if expected_version != 0:
                    raise ApiError(409, "ASSOCIATION_MEMBERSHIP_VERSION_CONFLICT", "成员关系已变化")
                row = AssociationCompanyMembership(
                    id=uuid.uuid4(),
                    association_tenant_id=association.tenant_id,
                    association_company_id=association.id,
                    member_tenant_id=member.tenant_id,
                    member_company_id=member.id,
                    version=1,
                )
                session.add(row)
            else:
                if row.version != expected_version:
                    raise ApiError(409, "ASSOCIATION_MEMBERSHIP_VERSION_CONFLICT", "成员关系已变化")
                row.version += 1
            row.member_tier = normalized_tier
            row.allocated_seats = allocated_seats
            row.benefits = benefits
            row.updated_by = actor.user_id
            await session.flush()
            await append_audit(
                session,
                tenant_id=association.tenant_id,
                company_id=association.id,
                actor_user_id=actor.user_id,
                action="platform.association.member.upsert",
                resource_type="association_company_membership",
                resource_id=row.id,
                trace_id=trace_id,
                event_data={
                    "member_company_id": str(member.id),
                    "member_tier": normalized_tier,
                    "allocated_seats": allocated_seats,
                    "benefit_keys": sorted(benefits),
                    "version": row.version,
                },
            )
            await session.refresh(row)
            return self._view(row, member)

    async def remove_member(
        self,
        *,
        actor: PlatformAssociationActor,
        association_company_id: uuid.UUID,
        member_company_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None,
    ) -> None:
        self._require_platform(actor)
        async with self._sessions() as session, session.begin():
            await self._scope(session, actor)
            association = await self._association(session, association_company_id)
            row = await session.scalar(
                select(AssociationCompanyMembership).where(
                    AssociationCompanyMembership.association_company_id
                    == association_company_id,
                    AssociationCompanyMembership.member_company_id == member_company_id,
                )
            )
            if row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "成员关系不存在")
            if row.version != expected_version:
                raise ApiError(409, "ASSOCIATION_MEMBERSHIP_VERSION_CONFLICT", "成员关系已变化")
            await append_audit(
                session,
                tenant_id=association.tenant_id,
                company_id=association.id,
                actor_user_id=actor.user_id,
                action="platform.association.member.remove",
                resource_type="association_company_membership",
                resource_id=row.id,
                trace_id=trace_id,
                event_data={"member_company_id": str(member_company_id), "version": row.version},
            )
            await session.execute(
                delete(AssociationCompanyMembership).where(
                    AssociationCompanyMembership.id == row.id
                )
            )

    @staticmethod
    def _require_platform(actor: PlatformAssociationActor) -> None:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可管理协会成员范围")

    @staticmethod
    async def _scope(session: AsyncSession, actor: PlatformAssociationActor) -> None:
        await set_rls_context(
            session,
            tenant_id=actor.tenant_id,
            company_id=actor.company_id,
            actor_user_id=actor.user_id,
            actor_session_id=actor.session_id,
        )

    @staticmethod
    async def _association(session: AsyncSession, company_id: uuid.UUID) -> Company:
        company = await session.get(Company, company_id)
        if company is None or company.deleted_at is not None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "协会不存在")
        if company.subject_type != "association":
            raise ApiError(422, "COMPANY_IS_NOT_ASSOCIATION", "所选主体不是协会或商会")
        return company

    @staticmethod
    def _view(
        membership: AssociationCompanyMembership, member: Company
    ) -> AssociationMemberView:
        return AssociationMemberView(
            id=membership.id,
            association_company_id=membership.association_company_id,
            company_id=member.id,
            legal_name=member.name,
            short_name=member.short_name,
            business_tenant_key=member.business_tenant_key,
            member_tier=membership.member_tier,
            allocated_seats=membership.allocated_seats,
            benefits=dict(membership.benefits),
            version=membership.version,
            updated_at=membership.updated_at,
        )


__all__ = [
    "AssociationMemberView",
    "AssociationSummaryView",
    "PlatformAssociationActor",
    "PlatformAssociationService",
]
