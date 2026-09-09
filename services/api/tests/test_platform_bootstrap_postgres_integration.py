from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.errors import ApiError
from app.cli.bootstrap_platform_admin import (
    PlatformBootstrapInput,
    bootstrap_platform_admin,
)
from app.cli.seed_content import (
    deterministic_id,
    load_content_package,
    seed_package,
)
from app.core.config import Settings
from app.core.tokens import decode_staff_access_token
from app.db.models import (
    AuditLog,
    Company,
    LifecycleStatus,
    Membership,
    ModelConfig,
    PromptVersion,
    Tenant,
    WeComUserBinding,
)
from app.integrations.wecom import WeComMember
from app.services.auth_store import AuthStore
from app.services.member_store import MemberScope, MemberStore
from app.services.wecom_store import WeComStore

ROOT = Path(__file__).resolve().parents[3]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
        reason="set RUN_PLATFORM_INTEGRATION=1 against a disposable migrated database",
    ),
]


@pytest.mark.asyncio
async def test_wecom_first_admin_auto_creation_is_idempotent_and_login_ready() -> None:
    settings = Settings()
    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    store = WeComStore(sessions, settings)
    corp_id = f"ww-integration-{uuid.uuid4().hex}"
    member = WeComMember(
        user_id="verified-admin",
        name="WeCom Admin",
        departments=(),
        position=None,
        avatar_url=None,
        status=1,
    )
    try:
        first = await store.resolve_or_bootstrap_identity(
            member=member,
            enterprise_name="WeCom Test Enterprise",
            corp_id=corp_id,
            allow_bootstrap=True,
        )
        second = await store.resolve_or_bootstrap_identity(
            member=member,
            enterprise_name="WeCom Test Enterprise",
            corp_id=corp_id,
            allow_bootstrap=True,
        )
        assert second == first
        authentication = await AuthStore(sessions, settings).authenticate_trusted_identity(
            user_id=first.user_id,
            membership_id=first.membership_id,
            tenant_id=first.tenant_id,
            company_id=first.company_id,
            account_hash=first.account_hash,
            event_type="staff.wecom_login",
        )
        assert authentication.identity.role == "company_admin"
        assert authentication.tokens.access_token
    finally:
        await runtime.dispose()


@pytest.mark.asyncio
async def test_wecom_members_auto_join_idempotently_with_scoped_non_admin_sessions() -> None:
    settings = Settings()
    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    store = WeComStore(sessions, settings)
    corp_id = f"ww-members-{uuid.uuid4().hex}"
    admin = WeComMember(
        user_id="admin", name="Admin", departments=(), position=None, avatar_url=None, status=1
    )
    member = replace(admin, user_id="ordinary-member", name="Association Member")

    async def join(corp: str, *, bootstrap: bool = False):
        return await store.resolve_or_bootstrap_identity(
            member=member, enterprise_name="Association", corp_id=corp, allow_bootstrap=bootstrap
        )

    try:
        with pytest.raises(ApiError, match="WECOM_AUTHORIZER_LOGIN_REQUIRED"):
            await join(corp_id)
        first = await store.resolve_or_bootstrap_identity(
            member=admin, enterprise_name="Association", corp_id=corp_id, allow_bootstrap=True
        )
        second, repeated = await asyncio.gather(join(corp_id), join(corp_id))
        assert repeated == second
        assert second.tenant_id == first.tenant_id
        assert second.company_id == first.company_id
        assert second.user_id != first.user_id
        assert await join(corp_id, bootstrap=True) == second
        authentication = await AuthStore(sessions, settings).authenticate_trusted_identity(
            user_id=second.user_id,
            membership_id=second.membership_id,
            tenant_id=second.tenant_id,
            company_id=second.company_id,
            account_hash=second.account_hash,
            event_type="staff.wecom_login",
        )
        assert authentication.tokens.access_token
        assert authentication.identity.role == "card_owner"
        assert not authentication.identity.must_change_password
        assert "card.write" in authentication.identity.permissions
        assert "company.manage" not in authentication.identity.permissions
        assert "members.manage" not in authentication.identity.permissions
        admin_auth = await AuthStore(sessions, settings).authenticate_trusted_identity(
            user_id=first.user_id,
            membership_id=first.membership_id,
            tenant_id=first.tenant_id,
            company_id=first.company_id,
            account_hash=first.account_hash,
            event_type="staff.wecom_login",
        )
        admin_principal = decode_staff_access_token(
            admin_auth.tokens.access_token,
            signing_key=settings.jwt_signing_key.get_secret_value(),
            issuer=settings.app_name,
        )
        members, _ = await MemberStore(sessions, settings).list_members(
            scope=MemberScope(
                tenant_id=first.tenant_id,
                company_id=first.company_id,
                actor_user_id=first.user_id,
                actor_session_id=admin_principal.session_id,
            ),
            limit=100,
            offset=0,
        )
        assert sum(row.membership_id == second.membership_id for row in members) == 1

        other_corp = f"ww-other-{uuid.uuid4().hex}"
        with pytest.raises(ApiError, match="WECOM_AUTHORIZER_LOGIN_REQUIRED"):
            await join(other_corp)
        await store.resolve_or_bootstrap_identity(
            member=admin, enterprise_name="Other Association",
            corp_id=other_corp, allow_bootstrap=True,
        )
        other = await join(other_corp)
        assert other.company_id != second.company_id
        assert other.user_id != second.user_id
        assert other.account_hash != second.account_hash
    finally:
        await runtime.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("disabled", ["membership", "binding", "company", "tenant"])
async def test_wecom_auto_join_never_reactivates_disabled_access(disabled: str) -> None:
    settings = Settings()
    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    store = WeComStore(sessions, settings)
    corp_id = f"ww-disabled-{uuid.uuid4().hex}"
    admin = WeComMember(
        user_id="admin", name="Admin", departments=(), position=None, avatar_url=None, status=1
    )
    member = replace(admin, user_id="member")
    try:
        await store.resolve_or_bootstrap_identity(
            member=admin, enterprise_name="Association", corp_id=corp_id, allow_bootstrap=True
        )
        identity = await store.resolve_or_bootstrap_identity(
            member=member, enterprise_name="Association", corp_id=corp_id, allow_bootstrap=False
        )
        async with owner.begin() as connection:
            if disabled == "membership":
                statement = update(Membership).where(Membership.id == identity.membership_id)
                statement = statement.values(status=LifecycleStatus.SUSPENDED)
            elif disabled == "binding":
                statement = update(WeComUserBinding).where(
                    WeComUserBinding.membership_id == identity.membership_id
                ).values(revoked_at=datetime.now(UTC))
            elif disabled == "company":
                statement = update(Company).where(Company.id == identity.company_id)
                statement = statement.values(status=LifecycleStatus.SUSPENDED)
            else:
                statement = update(Tenant).where(Tenant.id == identity.tenant_id)
                statement = statement.values(status=LifecycleStatus.SUSPENDED)
            await connection.execute(statement)
        with pytest.raises(ApiError) as denied:
            await store.resolve_or_bootstrap_identity(
                member=member, enterprise_name="Association",
                corp_id=corp_id, allow_bootstrap=True,
            )
        assert denied.value.code == "WECOM_ACCOUNT_DISABLED"
        if disabled in {"company", "tenant"}:
            with pytest.raises(ApiError) as new_member_denied:
                await store.resolve_or_bootstrap_identity(
                    member=replace(member, user_id="new-member"), enterprise_name="Association",
                    corp_id=corp_id, allow_bootstrap=False,
                )
            assert new_member_denied.value.code == "WECOM_ACCOUNT_DISABLED"
    finally:
        await runtime.dispose()
        await owner.dispose()


@pytest.mark.asyncio
async def test_seed_reuses_equivalent_ai_configuration_with_other_ids() -> None:
    settings = Settings()
    slug = f"seed-idempotency-{uuid.uuid4().hex[:12]}"
    package = load_content_package(
        ROOT / "packages" / "tenant-content" / "template.knowledge.json"
    )
    package = package.model_copy(
        update={
            "tenant": package.tenant.model_copy(
                update={"slug": slug, "name": "Seed Idempotency Tenant"}
            ),
            "company": package.company.model_copy(
                update={"slug": slug, "name": "Seed Idempotency Company"}
            ),
            "card": package.card.model_copy(update={"slug": slug}),
        }
    )
    tenant_id = deterministic_id(slug, "tenant")
    company_id = deterministic_id(slug, "company")
    replacement_prompt_id = uuid.uuid4()
    replacement_model_id = uuid.uuid4()
    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    try:
        async with sessions() as session, session.begin():
            await seed_package(session, package, settings)

        async with owner.begin() as connection:
            await connection.execute(
                update(PromptVersion)
                .where(
                    PromptVersion.tenant_id == tenant_id,
                    PromptVersion.company_id == company_id,
                )
                .values(id=replacement_prompt_id)
            )
            await connection.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.tenant_id == tenant_id,
                    ModelConfig.company_id == company_id,
                )
                .values(id=replacement_model_id)
            )

        async with sessions() as session, session.begin():
            await seed_package(session, package, settings)

        async with owner.connect() as connection:
            prompt_ids = (
                await connection.execute(
                    select(PromptVersion.id).where(
                        PromptVersion.tenant_id == tenant_id,
                        PromptVersion.company_id == company_id,
                    )
                )
            ).scalars().all()
            model_ids = (
                await connection.execute(
                    select(ModelConfig.id).where(
                        ModelConfig.tenant_id == tenant_id,
                        ModelConfig.company_id == company_id,
                    )
                )
            ).scalars().all()
        assert prompt_ids == [replacement_prompt_id]
        assert model_ids == [replacement_model_id]
    finally:
        await runtime.dispose()
        await owner.dispose()


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_audited_and_login_ready() -> None:
    settings = Settings()
    suffix = uuid.uuid4().hex[:12]
    account = f"platform-{suffix}@example.test"
    password = "Integration-Platform-Password-2026!"  # noqa: S105
    bootstrap = PlatformBootstrapInput(
        _env_file=None,
        tenant_slug="template",
        account=account,
        password=password,
        display_name="Platform Integration Admin",
        confirm="CREATE_FIRST_PLATFORM_ADMIN",
    )

    first = await bootstrap_platform_admin(settings, bootstrap)
    second = await bootstrap_platform_admin(settings, bootstrap)

    assert first.created is True
    assert second.created is False
    assert second.tenant_id == first.tenant_id
    assert second.company_id == first.company_id
    assert second.user_id == first.user_id
    assert second.membership_id == first.membership_id

    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    try:
        authentication = await AuthStore(
            async_sessionmaker(runtime, expire_on_commit=False),
            settings,
        ).login(account=account, credential=password)
        assert authentication.identity.role == "platform_admin"
        assert authentication.identity.permissions == ("*",)

        async with owner.connect() as connection:
            action = await connection.scalar(
                select(AuditLog.action).where(
                    AuditLog.resource_id == uuid.UUID(first.membership_id)
                )
            )
        assert action == "platform.admin.bootstrap"
    finally:
        await runtime.dispose()
        await owner.dispose()
