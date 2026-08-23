from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    TemporaryCredentialDelivery,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.core.staff_auth import hash_staff_password, normalize_staff_account
from app.db.models import (
    AuditLog,
    Card,
    CardKind,
    Company,
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
from app.services.platform_identity import (
    business_tenant_key as _business_tenant_key,
)
from app.services.platform_identity import (
    generate_temporary_password as _generate_temporary_password,
)
from app.services.platform_identity import (
    tenant_slug_from_business_key as _tenant_slug_from_business_key,
)


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
        "SELECT app.platform_operations_tasks("
        ":company_id, :status, :task_type, :updated_from, :updated_to, :limit, :offset)"
    ),
    "platform_operations_task_groups": text(
        "SELECT app.platform_operations_task_groups("
        ":company_id, :status, :task_type, :updated_from, :updated_to, :limit, :offset)"
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
        legal_name = body.legal_name.strip()
        short_name = body.short_name.strip() if body.short_name else None
        business_tenant_key = _business_tenant_key(
            subject_type=body.subject_type,
            social_credit_code=body.social_credit_code,
            company_id=company_id,
        )
        tenant_slug = _tenant_slug_from_business_key(business_tenant_key)
        now = datetime.now(UTC)
        temporary_password = _generate_temporary_password()
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
                {"key": f"platform-enterprise:{business_tenant_key}"},
            )
            duplicate_tenant = await session.scalar(
                select(Tenant.id).where(Tenant.slug == tenant_slug)
            )
            if duplicate_tenant is not None:
                raise ApiError(409, "TENANT_SLUG_CONFLICT", "系统生成的企业租户标识冲突")
            duplicate_business_key = await session.scalar(
                select(Company.id).where(Company.business_tenant_key == business_tenant_key)
            )
            if duplicate_business_key is not None:
                raise ApiError(409, "BUSINESS_TENANT_KEY_CONFLICT", "企业业务标识已存在")
            duplicate_account = await session.scalar(
                select(StaffCredential.id).where(StaffCredential.account_normalized == account)
            )
            if duplicate_account is not None:
                raise ApiError(409, "ACCOUNT_CONFLICT", "管理员登录账号已存在")
            tenant = Tenant(
                id=tenant_id,
                slug=tenant_slug,
                name=short_name or legal_name,
                tenant_type=TenantType.ENTERPRISE,
                status=LifecycleStatus.ACTIVE,
                settings={"slug": tenant_slug, "onboarding_status": "initialized"},
            )
            company = Company(
                id=company_id,
                tenant_id=tenant_id,
                name=legal_name,
                normalized_name=" ".join(legal_name.casefold().split()),
                short_name=short_name,
                subject_type=body.subject_type,
                social_credit_code=body.social_credit_code,
                business_tenant_key=business_tenant_key,
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
                        "plan_code": body.default_plan_code,
                        "billing_cycle": "contract",
                        "contract_price_cny": None,
                        "feature_overrides": {},
                        "service_valid_until": None,
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
                password_hash=hash_staff_password(temporary_password),
                is_enabled=True,
                must_change_password=True,
                temporary_password_expires_at=(now + timedelta(days=7)).replace(microsecond=0),
            )
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
                "tenant_slug": tenant_slug,
                "business_tenant_key": business_tenant_key,
                "admin_membership_id": str(membership_id),
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
                tenant_slug=tenant_slug,
                tenant_name=tenant.name,
                company_id=company_id,
                company_name=company.name,
                legal_name=company.name,
                short_name=company.short_name,
                subject_type=body.subject_type,
                social_credit_code=body.social_credit_code,
                business_tenant_key=business_tenant_key,
                company_status=company.status.value,
                admin_user_id=user_id,
                admin_membership_id=membership_id,
                credential_delivery=TemporaryCredentialDelivery(
                    account=account,
                    temporary_password=temporary_password,
                    expires_at=credential.temporary_password_expires_at or now,
                    shown_once=True,
                ),
                created_at=now,
            )

    async def list_enterprises(
        self,
        *,
        actor: PlatformActor,
        search: str | None,
        status: str | None,
        activity_level: str | None,
        has_actionable_tasks: bool | None,
        service_risk: str | None,
        sort_by: str,
        sort_order: str,
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
                    ":search, :status, :activity_level, :has_actionable_tasks, "
                    ":service_risk, :sort_by, :sort_order, :limit, :offset)"
                ),
                {
                    "search": search,
                    "status": status,
                    "activity_level": activity_level,
                    "has_actionable_tasks": has_actionable_tasks,
                    "service_risk": service_risk,
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                    "limit": limit,
                    "offset": offset,
                },
            )
            data = _json_object(payload)
            records = [
                _enterprise_list_item_from_payload(item)
                for item in data.get("data", [])
                if isinstance(item, dict)
            ]
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
            return _overview_from_payload(_json_object(payload))

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
            return _enterprise_detail_from_payload(detail_payload)

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
            params={"limit": limit, "offset": offset},
        )
        return (
            [
                _company_aggregate_from_payload(item)
                for item in payload.get("data", [])
                if isinstance(item, dict)
            ],
            int(payload.get("total", 0)),
        )

    async def list_tasks(
        self,
        *,
        actor: PlatformActor,
        view: str,
        company_id: uuid.UUID | None,
        status: str | None,
        task_type: str | None,
        updated_from: datetime | None,
        updated_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[list[PlatformTaskRecord], list[dict[str, object]], int]:
        payload = await self._list_platform_read_model(
            actor=actor,
            function="platform_operations_tasks",
            params={
                "company_id": company_id,
                "status": status,
                "task_type": task_type,
                "updated_from": updated_from,
                "updated_to": updated_to,
                "limit": limit,
                "offset": offset,
            },
        )
        records = [
            _platform_task_from_payload(item)
            for item in payload.get("data", [])
            if isinstance(item, dict)
        ]
        groups: list[dict[str, object]] = []
        if view == "company":
            grouped_payload = await self._list_platform_read_model(
                actor=actor,
                function="platform_operations_task_groups",
                params={
                    "company_id": company_id,
                    "status": status,
                    "task_type": task_type,
                    "updated_from": updated_from,
                    "updated_to": updated_to,
                    "limit": limit,
                    "offset": offset,
                },
            )
            groups = [
                item
                for item in grouped_payload.get("groups", [])
                if isinstance(item, dict)
            ]
        return records, groups, int(payload.get("total", 0))

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
            params={"limit": limit, "offset": offset},
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
        params: dict[str, object],
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
                params,
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


def _optional_timestamp(value: object) -> object:
    if value in {"-infinity", "infinity"}:
        return None
    return value


def _overview_from_payload(payload: dict[str, object]) -> PlatformOverviewRecord:
    return PlatformOverviewRecord.model_validate(
        {
            "generated_at": payload.get("generated_at"),
            "enabled_enterprise_count": payload.get(
                "enabled_enterprise_count",
                payload.get("enterprise_count", 0),
            ),
            "active_enterprise_30d_count": payload.get(
                "active_enterprise_30d_count",
                payload.get("active_enterprise_count", 0),
            ),
            "pending_activation_count": payload.get(
                "pending_activation_count",
                payload.get("onboarding_count", 0),
            ),
            "published_card_count": payload.get("published_card_count", 0),
            "visits_30d": payload.get("visits_30d", 0),
            "unique_visitors_30d": payload.get("unique_visitors_30d", 0),
            "conversations_30d": payload.get("conversations_30d", 0),
            "consented_leads_30d": payload.get(
                "consented_leads_30d",
                payload.get("leads_30d", 0),
            ),
            "pending_task_count": payload.get("pending_task_count", 0),
            "failed_task_count": payload.get("failed_task_count", 0),
            "service_risk_count": payload.get("service_risk_count", 0),
            "llm_ready": payload.get("llm_ready", False),
            "import_ready": payload.get("import_ready", False),
        }
    )


def _enterprise_list_item_from_payload(payload: dict[str, object]) -> EnterpriseListItem:
    tenant_slug = str(payload.get("tenant_slug") or "")
    company_name = str(payload.get("company_name") or payload.get("legal_name") or "")
    created_at = payload.get("created_at")
    return EnterpriseListItem.model_validate(
        {
            "tenant_id": payload.get("tenant_id"),
            "tenant_slug": tenant_slug,
            "tenant_name": payload.get("tenant_name"),
            "company_id": payload.get("company_id"),
            "company_name": company_name,
            "legal_name": payload.get("legal_name", company_name),
            "short_name": payload.get("short_name"),
            "subject_type": payload.get("subject_type", "domestic_enterprise"),
            "social_credit_code": payload.get("social_credit_code"),
            "business_tenant_key": payload.get(
                "business_tenant_key",
                tenant_slug.upper() if tenant_slug else "UNKNOWN",
            ),
            "status": payload.get("status"),
            "employee_count": payload.get("employee_count", 0),
            "card_count": payload.get("card_count", 0),
            "published_card_count": payload.get("published_card_count", 0),
            "visits_30d": payload.get("visits_30d", 0),
            "unique_visitors_30d": payload.get("unique_visitors_30d", 0),
            "conversations_30d": payload.get("conversations_30d", 0),
            "consented_leads_30d": payload.get(
                "consented_leads_30d",
                payload.get("leads_30d", 0),
            ),
            "actionable_task_count": payload.get("actionable_task_count", 0),
            "failed_task_count": payload.get("failed_task_count", 0),
            "profile_completion": payload.get("profile_completion", 0),
            "service_valid_until": payload.get("service_valid_until"),
            "service_risk_level": payload.get("service_risk_level", "missing"),
            "last_activity_at": _optional_timestamp(payload.get("last_activity_at")),
            "created_at": created_at,
            "updated_at": payload.get("updated_at", created_at),
        }
    )


def _enterprise_detail_from_payload(payload: dict[str, object]) -> PlatformEnterpriseDetail:
    company_name = str(payload.get("company_name") or payload.get("legal_name") or "")
    cards = payload.get("cards")
    return PlatformEnterpriseDetail.model_validate(
        {
            "tenant_id": payload.get("tenant_id"),
            "tenant_slug": payload.get("tenant_slug"),
            "tenant_name": payload.get("tenant_name"),
            "company_id": payload.get("company_id"),
            "company_name": company_name,
            "legal_name": payload.get("legal_name", company_name),
            "short_name": payload.get("short_name"),
            "subject_type": payload.get("subject_type", "domestic_enterprise"),
            "social_credit_code": payload.get("social_credit_code"),
            "business_tenant_key": payload.get(
                "business_tenant_key",
                str(payload.get("tenant_slug") or "").upper() or "UNKNOWN",
            ),
            "status": payload.get("status"),
            "version": payload.get("version"),
            "onboarding_status": payload.get("onboarding_status", "content_pending"),
            "profile_completion": payload.get("profile_completion", 0),
            "employee_count": payload.get("employee_count", 0),
            "card_count": payload.get("card_count", 0),
            "published_card_count": payload.get("published_card_count", 0),
            "visits_30d": payload.get("visits_30d", 0),
            "unique_visitors_30d": payload.get("unique_visitors_30d", 0),
            "conversations_30d": payload.get("conversations_30d", 0),
            "consented_leads_30d": payload.get(
                "consented_leads_30d",
                payload.get("leads_30d", 0),
            ),
            "actionable_task_count": payload.get("actionable_task_count", 0),
            "failed_task_count": payload.get("failed_task_count", 0),
            "service_valid_until": payload.get("service_valid_until"),
            "service_risk_level": payload.get("service_risk_level", "missing"),
            "last_activity_at": _optional_timestamp(payload.get("last_activity_at")),
            "cards": cards if isinstance(cards, list) else [],
            "business_profile": payload.get("business_profile", []),
            "recent_tasks": payload.get("recent_tasks", []),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
    )


def _company_aggregate_from_payload(payload: dict[str, object]) -> PlatformCompanyAggregate:
    company_name = str(payload.get("company_name") or payload.get("legal_name") or "")
    return PlatformCompanyAggregate.model_validate(
        {
            "company_id": payload.get("company_id"),
            "company_name": company_name,
            "legal_name": payload.get("legal_name", company_name),
            "short_name": payload.get("short_name"),
            "business_tenant_key": payload.get(
                "business_tenant_key",
                company_name.upper().replace(" ", "-")[:32] or "UNKNOWN",
            ),
            "status": payload.get("status", "active"),
            "employee_count": payload.get("employee_count", 0),
            "card_count": payload.get("card_count", 0),
            "published_card_count": payload.get("published_card_count", 0),
            "visits_30d": payload.get("visits_30d", 0),
            "unique_visitors_30d": payload.get("unique_visitors_30d", 0),
            "conversations_30d": payload.get("conversations_30d", 0),
            "consented_leads_30d": payload.get(
                "consented_leads_30d",
                payload.get("leads_30d", 0),
            ),
            "actionable_task_count": payload.get("actionable_task_count", 0),
            "failed_task_count": payload.get("failed_task_count", 0),
            "service_valid_until": payload.get("service_valid_until"),
            "service_risk_level": payload.get("service_risk_level", "missing"),
            "last_activity_at": _optional_timestamp(
                payload.get("last_activity_at", payload.get("last_visit_at"))
            ),
        }
    )


def _platform_task_from_payload(payload: dict[str, object]) -> PlatformTaskRecord:
    task_type = str(payload.get("task_type") or "enterprise_risk")
    if task_type == "outbox":
        task_type = "enterprise_risk"
    if task_type not in {
        "onboarding",
        "knowledge_import",
        "content_review",
        "enterprise_risk",
        "service_validity",
    }:
        task_type = "enterprise_risk"
    status = _normalize_task_status(str(payload.get("status") or "pending"))
    return PlatformTaskRecord.model_validate(
        {
            "id": payload.get("id"),
            "task_type": task_type,
            "business_label": payload.get("business_label", "运营事项"),
            "status": status,
            "company_id": payload.get("company_id"),
            "company_name": payload.get("company_name"),
            "tenant_slug": payload.get("tenant_slug"),
            "error_code": payload.get("error_code"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at", payload.get("created_at")),
        }
    )


def _normalize_task_status(value: str) -> str:
    mapping = {
        "queued": "pending",
        "processing": "in_progress",
        "retry_scheduled": "blocked",
        "dead_letter": "failed",
        "failed": "failed",
        "completed": "completed",
        "completed_with_errors": "failed",
        "cancelled": "cancelled",
        "expired": "expired",
        "draft": "pending",
        "review": "pending",
        "manual_required": "blocked",
        "ready_to_confirm": "pending",
        "confirmed": "completed",
    }
    return mapping.get(value, value if value in mapping.values() else "pending")


__all__ = ["PlatformActor", "PlatformStore"]
