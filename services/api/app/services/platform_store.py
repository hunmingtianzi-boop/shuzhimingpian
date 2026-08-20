from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.platform_schemas import (
    CreateEnterpriseRequest,
    EnterpriseListItem,
    EnterpriseRecord,
    PlatformAuditRecord,
    PlatformCompanyAggregate,
    PlatformEnterpriseDetail,
    PlatformEnterpriseLifecycleRecord,
    PlatformOverviewRecord,
    PlatformTaskRecord,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.core.staff_auth import hash_staff_password, normalize_staff_account
from app.db.models import (
    AuditLog,
    Card,
    CardKind,
    Company,
    ContentStatus,
    LifecycleStatus,
    Membership,
    MembershipRole,
    OutboxEvent,
    OutboxStatus,
    PlatformOnboardingSession,
    StaffCredential,
    Tenant,
    TenantType,
    User,
)
from app.db.session import set_rls_context


@dataclass(frozen=True, slots=True)
class PlatformActor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    role: str


_COMPANY_ADMIN_PERMISSIONS = [
    "company.manage",
    "card.manage",
    "knowledge.manage",
    "knowledge.publish",
    "catalog.manage",
    "conversations.read",
    "summaries.write",
    "leads.read",
    "leads.write",
    "privacy.manage",
    "analytics.read",
]
_READ_MODEL_STATEMENTS = {
    "platform_operations_company_aggregates": text(
        "SELECT app.platform_operations_company_aggregates(:limit, :offset)"
    ),
    "platform_operations_tasks": text(
        "SELECT app.platform_operations_tasks(:limit, :offset)"
    ),
    "platform_operations_audit": text(
        "SELECT app.platform_operations_audit(:limit, :offset)"
    ),
}


class PlatformStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        public_card_base_url: str | None = None,
    ) -> None:
        self._sessions = session_factory
        self._cipher = PiiCipher.from_settings(settings)
        if public_card_base_url is None:
            public_card_base_url = next(
                (
                    origin
                    for origin in settings.cors_allowed_origins
                    if origin.startswith(("https://", "http://localhost", "http://127.0.0.1"))
                ),
                "http://127.0.0.1:4173",
            )
        self._public_card_base_url = _normalize_public_card_base_url(
            public_card_base_url,
            allow_insecure_http=settings.allow_insecure_public_card_http,
        )

    async def create_enterprise(
        self,
        *,
        actor: PlatformActor,
        body: CreateEnterpriseRequest,
        trace_id: str | None,
    ) -> EnterpriseRecord:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可开通企业")
        account = normalize_staff_account(body.admin_account)
        tenant_id = uuid.uuid4()
        company_id = uuid.uuid4()
        user_id = uuid.uuid4()
        membership_id = uuid.uuid4()
        credential_id = uuid.uuid4()
        card_id = uuid.uuid4()
        card_slug = f"c-{secrets.token_hex(16)}"
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"platform-enterprise:{body.tenant_slug}"},
            )
            duplicate_tenant = await session.scalar(
                select(Tenant.id).where(Tenant.slug == body.tenant_slug)
            )
            if duplicate_tenant is not None:
                raise ApiError(409, "TENANT_SLUG_CONFLICT", "企业租户标识已存在")
            duplicate_account = await session.scalar(
                select(StaffCredential.id).where(StaffCredential.account_normalized == account)
            )
            if duplicate_account is not None:
                raise ApiError(409, "ACCOUNT_CONFLICT", "管理员登录账号已存在")
            tenant = Tenant(
                id=tenant_id,
                slug=body.tenant_slug,
                name=body.tenant_name,
                tenant_type=TenantType.ENTERPRISE,
                status=LifecycleStatus.ACTIVE,
                settings={"slug": body.tenant_slug, "onboarding_status": "initialized"},
            )
            company = Company(
                id=company_id,
                tenant_id=tenant_id,
                name=body.company_name,
                normalized_name=" ".join(body.company_name.casefold().split()),
                industry=body.industry,
                status=LifecycleStatus.ACTIVE,
                settings={
                    "summary": "",
                    "region": None,
                    "website": None,
                    "logo_url": None,
                    "onboarding_status": "content_pending",
                    "policy_versions": {
                        "profile_personalization": "profile-personalization-v1"
                    },
                    "commercial_entitlements": {
                        "plan_code": "starter",
                        "billing_cycle": "contract",
                        "contract_price_cny": None,
                        "feature_overrides": {},
                    },
                },
            )
            email = account if "@" in account else None
            user = User(
                id=user_id,
                display_name=body.admin_display_name,
                email_ciphertext=self._cipher.encrypt(email) if email else None,
                email_hmac=self._cipher.hmac(email) if email else None,
                status=LifecycleStatus.ACTIVE,
            )
            membership_values = {
                "id": membership_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "role": MembershipRole.COMPANY_ADMIN,
                "permissions": _COMPANY_ADMIN_PERMISSIONS,
                "status": LifecycleStatus.ACTIVE,
            }
            credential = StaffCredential(
                id=credential_id,
                user_id=user_id,
                membership_id=membership_id,
                tenant_id=tenant_id,
                company_id=company_id,
                account_normalized=account,
                password_hash=hash_staff_password(body.admin_password.get_secret_value()),
                is_enabled=True,
            )
            card_values = {
                "id": card_id,
                "tenant_id": tenant_id,
                "company_id": company_id,
                "card_kind": CardKind.ENTERPRISE,
                "owner_user_id": None,
                "responsible_user_id": user_id,
                "slug": card_slug,
                "display_name": body.company_name,
                "status": ContentStatus.DRAFT,
                "settings": {
                    "title": body.initial_card_title or body.company_name,
                    "assistant_name": "企业 AI 接待",
                    "welcome_message": "您好，我可以根据企业已审核资料为您介绍业务。",
                    "suggested_questions": [],
                    "policy_versions": {
                        "privacy": "privacy-v1",
                        "chat_notice": "chat-notice-v1",
                        "lead_consent": "lead-consent-v1",
                        "profile_personalization": "profile-personalization-v1",
                    },
                },
            }
            # These mappers intentionally do not expose ORM relationships. Flush in
            # foreign-key order so SQLAlchemy cannot emit a child row before its
            # parent while onboarding a completely new tenant.
            session.add_all([tenant, user])
            await session.flush()
            session.add(company)
            await session.flush()
            # Avoid INSERT .. RETURNING here. PostgreSQL correctly applies SELECT
            # RLS policies to RETURNING rows, while this onboarding capability is
            # intentionally INSERT-only for cross-tenant membership/card/event/audit
            # data.
            await session.execute(insert(Membership).values(**membership_values))
            await session.execute(insert(Card).values(**card_values))
            session.add(credential)
            await session.flush()
            await session.execute(
                insert(OutboxEvent).values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    company_id=company_id,
                    aggregate_type="company",
                    aggregate_id=company_id,
                    aggregate_version=1,
                    event_type="enterprise.created.v1",
                    payload={
                        "tenant_id": str(tenant_id),
                        "company_id": str(company_id),
                        "admin_user_id": str(user_id),
                    },
                    headers={"contains_pii": False},
                    deduplication_key=f"enterprise.created:{company_id}",
                    status=OutboxStatus.PENDING,
                )
            )
            audit_event = {
                "tenant_slug": body.tenant_slug,
                "admin_membership_id": str(membership_id),
                "initial_card_id": str(card_id),
            }
            audit_payload = {
                "tenant_id": str(tenant_id),
                "company_id": str(company_id),
                "actor_user_id": str(actor.user_id),
                "action": "platform.enterprise.create",
                "resource_type": "company",
                "resource_id": str(company_id),
                "trace_id": trace_id,
                "event_data": audit_event,
                "previous_hash": None,
            }
            await session.execute(
                insert(AuditLog).values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    company_id=company_id,
                    actor_user_id=actor.user_id,
                    action="platform.enterprise.create",
                    resource_type="company",
                    resource_id=company_id,
                    trace_id=trace_id,
                    event_data=audit_event,
                    previous_hash=None,
                    entry_hash=hashlib.sha256(
                        json.dumps(
                            audit_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                )
            )
            return EnterpriseRecord(
                tenant_id=tenant_id,
                tenant_slug=body.tenant_slug,
                tenant_name=tenant.name,
                company_id=company_id,
                company_name=company.name,
                company_status=company.status.value,
                admin_user_id=user_id,
                admin_membership_id=membership_id,
                initial_card_id=card_id,
                initial_card_slug=card_slug,
                created_at=now,
            )

    async def list_enterprises(
        self,
        *,
        actor: PlatformActor,
        search: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[EnterpriseListItem], int]:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可查看企业清单")
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            payload = await session.scalar(
                text(
                    "SELECT app.platform_operations_enterprises("
                    ":search, :status, :limit, :offset)"
                ),
                {
                    "search": search,
                    "status": status,
                    "limit": limit,
                    "offset": offset,
                },
            )
            data = _json_object(payload)
            records = [EnterpriseListItem.model_validate(item) for item in data.get("data", [])]
            return records, int(data.get("total", 0))

    async def get_overview(self, *, actor: PlatformActor) -> PlatformOverviewRecord:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可查看平台总览")
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            payload = await session.scalar(
                text("SELECT app.platform_operations_overview()")
            )
            return PlatformOverviewRecord.model_validate(_json_object(payload))

    async def get_enterprise_detail(
        self,
        *,
        actor: PlatformActor,
        company_id: uuid.UUID,
    ) -> PlatformEnterpriseDetail:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可查看企业详情")
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            payload = await session.scalar(
                text(
                    "SELECT app.platform_operations_enterprise_detail("
                    ":company_id, :public_card_base_url)"
                ),
                {
                    "company_id": company_id,
                    "public_card_base_url": self._public_card_base_url,
                },
            )
            if payload is None:
                raise ApiError(404, "ENTERPRISE_NOT_FOUND", "企业不存在")
            detail_payload = _json_object(payload)
            card_kind_rows = (
                await session.execute(
                    select(Card.id, Card.card_kind).where(
                        Card.company_id == company_id,
                        Card.deleted_at.is_(None),
                    )
                )
            ).all()
            card_kinds = {str(card_id): card_kind.value for card_id, card_kind in card_kind_rows}
            for card_payload in detail_payload.get("cards", []):
                if isinstance(card_payload, dict):
                    card_payload["card_kind"] = card_kinds.get(
                        str(card_payload.get("id")), CardKind.EMPLOYEE.value
                    )
            business_profile = await session.scalar(
                select(PlatformOnboardingSession.business_profile)
                .where(PlatformOnboardingSession.company_id == company_id)
                .order_by(PlatformOnboardingSession.updated_at.desc())
                .limit(1)
            )
            detail_payload["business_profile"] = list(business_profile or [])
            return PlatformEnterpriseDetail.model_validate(detail_payload)

    async def transition_enterprise(
        self,
        *,
        actor: PlatformActor,
        company_id: uuid.UUID,
        expected_version: int,
        target_status: str,
        reason: str,
        trace_id: str | None,
    ) -> PlatformEnterpriseLifecycleRecord:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可变更企业状态")
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            payload = _json_object(
                await session.scalar(
                    text(
                        "SELECT app.platform_operations_transition_enterprise("
                        ":company_id, :expected_version, :target_status)"
                    ),
                    {
                        "company_id": company_id,
                        "expected_version": expected_version,
                        "target_status": target_status,
                    },
                )
            )
            outcome = payload.get("outcome")
            if outcome == "not_found":
                raise ApiError(404, "ENTERPRISE_NOT_FOUND", "企业不存在")
            if outcome == "version_conflict":
                raise ApiError(409, "VERSION_CONFLICT", "企业状态已变化，请刷新后重试")
            if outcome not in {"succeeded", "unchanged"}:
                raise RuntimeError("enterprise lifecycle function returned an invalid outcome")

            changed = outcome == "succeeded"
            record = PlatformEnterpriseLifecycleRecord.model_validate(
                {
                    "tenant_id": payload.get("tenant_id"),
                    "company_id": payload.get("company_id"),
                    "previous_status": payload.get("previous_status"),
                    "status": payload.get("status"),
                    "version": payload.get("version"),
                    "changed": changed,
                    "updated_at": payload.get("updated_at"),
                }
            )
            if not changed:
                return record

            action = (
                "platform.enterprise.resume"
                if record.status == LifecycleStatus.ACTIVE.value
                else "platform.enterprise.suspend"
            )
            event_data = {
                "previous_status": record.previous_status,
                "status": record.status,
                "reason": reason,
                "version": record.version,
            }
            previous_hash = payload.get("previous_audit_hash")
            audit_payload = {
                "tenant_id": str(record.tenant_id),
                "company_id": str(record.company_id),
                "actor_user_id": str(actor.user_id),
                "action": action,
                "resource_type": "company",
                "resource_id": str(record.company_id),
                "trace_id": trace_id,
                "event_data": event_data,
                "previous_hash": previous_hash,
            }
            await session.execute(
                insert(AuditLog).values(
                    id=uuid.uuid4(),
                    tenant_id=record.tenant_id,
                    company_id=record.company_id,
                    actor_user_id=actor.user_id,
                    action=action,
                    resource_type="company",
                    resource_id=record.company_id,
                    trace_id=trace_id,
                    event_data=event_data,
                    previous_hash=previous_hash,
                    entry_hash=hashlib.sha256(
                        json.dumps(
                            audit_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest(),
                )
            )
            await session.execute(
                insert(OutboxEvent).values(
                    id=uuid.uuid4(),
                    tenant_id=record.tenant_id,
                    company_id=record.company_id,
                    aggregate_type="company",
                    aggregate_id=record.company_id,
                    aggregate_version=record.version,
                    event_type=f"enterprise.{record.status}.v1",
                    payload={
                        "tenant_id": str(record.tenant_id),
                        "company_id": str(record.company_id),
                        "status": record.status,
                        "version": record.version,
                    },
                    headers={"contains_pii": False},
                    deduplication_key=(
                        f"enterprise.lifecycle:{record.company_id}:{record.version}"
                    ),
                    status=OutboxStatus.PENDING,
                )
            )
            return record

    async def list_company_aggregates(
        self,
        *,
        actor: PlatformActor,
        limit: int,
        offset: int,
    ) -> tuple[list[PlatformCompanyAggregate], int]:
        payload = await self._list_platform_read_model(
            actor=actor,
            function="platform_operations_company_aggregates",
            limit=limit,
            offset=offset,
        )
        return (
            [
                PlatformCompanyAggregate.model_validate(item)
                for item in payload.get("data", [])
            ],
            int(payload.get("total", 0)),
        )

    async def list_tasks(
        self,
        *,
        actor: PlatformActor,
        limit: int,
        offset: int,
    ) -> tuple[list[PlatformTaskRecord], int]:
        payload = await self._list_platform_read_model(
            actor=actor,
            function="platform_operations_tasks",
            limit=limit,
            offset=offset,
        )
        return (
            [PlatformTaskRecord.model_validate(item) for item in payload.get("data", [])],
            int(payload.get("total", 0)),
        )

    async def list_audit(
        self,
        *,
        actor: PlatformActor,
        limit: int,
        offset: int,
    ) -> tuple[list[PlatformAuditRecord], int]:
        payload = await self._list_platform_read_model(
            actor=actor,
            function="platform_operations_audit",
            limit=limit,
            offset=offset,
        )
        return (
            [PlatformAuditRecord.model_validate(item) for item in payload.get("data", [])],
            int(payload.get("total", 0)),
        )

    async def _list_platform_read_model(
        self,
        *,
        actor: PlatformActor,
        function: str,
        limit: int,
        offset: int,
    ) -> dict[str, object]:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可查看平台运营数据")
        statement = _READ_MODEL_STATEMENTS.get(function)
        if statement is None:
            raise ValueError("unsupported platform read model")
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=actor.tenant_id,
                company_id=actor.company_id,
                actor_user_id=actor.user_id,
                actor_session_id=actor.session_id,
            )
            payload = await session.scalar(
                statement,
                {"limit": limit, "offset": offset},
            )
            return _json_object(payload)


def _normalize_public_card_base_url(
    value: str,
    *,
    allow_insecure_http: bool = False,
) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("public_card_base_url must be an absolute HTTP(S) base URL")
    if (
        parsed.scheme == "http"
        and parsed.hostname not in {"localhost", "127.0.0.1"}
        and not allow_insecure_http
    ):
        raise ValueError("non-local public_card_base_url must use HTTPS")
    return candidate


def _json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("platform read model returned an invalid payload")
    return value


__all__ = ["PlatformActor", "PlatformStore"]
