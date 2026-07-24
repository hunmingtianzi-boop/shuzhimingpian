from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.prompts import DEFAULT_PROMPT_VERSION
from app.api.errors import ApiError
from app.api.platform_schemas import (
    ConfirmPlatformOnboardingRequest,
    CreateEnterpriseRequest,
    StartPlatformOnboardingRequest,
)
from app.core.config import Settings
from app.services.knowledge_import_store import KnowledgeImportStore, PendingImport
from app.services.platform_onboarding import PlatformOnboardingService
from app.services.platform_store import PlatformActor, PlatformStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
        reason="set RUN_PLATFORM_INTEGRATION=1 against a disposable migrated database",
    ),
]


@pytest.mark.asyncio
async def test_platform_admin_can_onboard_a_login_ready_enterprise_through_rls() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    runtime = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    actor_tenant_id, actor_company_id, actor_user_id, membership_id, session_id = [
        uuid.uuid4() for _ in range(5)
    ]
    actor_slug = f"platform-integration-{uuid.uuid4().hex[:10]}"
    enterprise_slug = f"enterprise-integration-{uuid.uuid4().hex[:10]}"
    try:
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO tenants(id,slug,name,type,status,settings) "
                    "VALUES (:id,:slug,'Platform Integration','chamber','active','{}')"
                ),
                {"id": actor_tenant_id, "slug": actor_slug},
            )
            await connection.execute(
                text(
                    "INSERT INTO companies(id,tenant_id,name,normalized_name,status,settings) "
                    "VALUES (:id,:tenant_id,'Platform Integration',"
                    "'platform integration','active','{}')"
                ),
                {"id": actor_company_id, "tenant_id": actor_tenant_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO users(id,display_name,status) "
                    "VALUES (:id,'Platform Integration','active')"
                ),
                {"id": actor_user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO memberships("
                    "id,user_id,tenant_id,company_id,role,permissions,status) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,'platform_admin',"
                    "ARRAY['*'],'active')"
                ),
                {
                    "id": membership_id,
                    "user_id": actor_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO auth_sessions(id,user_id,tenant_id,company_id,"
                    "refresh_token_hash,expires_at) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,:token_hash,:expires_at)"
                ),
                {
                    "id": session_id,
                    "user_id": actor_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                    "token_hash": uuid.uuid4().hex,
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                },
            )
        store = PlatformStore(sessions, settings)
        actor = PlatformActor(
            user_id=actor_user_id,
            tenant_id=actor_tenant_id,
            company_id=actor_company_id,
            session_id=session_id,
            role="platform_admin",
        )
        body = CreateEnterpriseRequest(
            tenant_slug=enterprise_slug,
            tenant_name="Integration Enterprise",
            company_name="Integration Enterprise Co",
            industry="AI",
            admin_account=f"{enterprise_slug}@example.test",
            admin_display_name="Integration Admin",
            admin_password=SecretStr("Integration-Password-2026!"),
            initial_card_title="Integration Card",
        )
        created = await store.create_enterprise(
            actor=actor,
            body=body,
            trace_id="platform-postgres-integration",
        )
        rows, _ = await store.list_enterprises(
            actor=actor,
            search=None,
            status=None,
            limit=100,
            offset=0,
        )
        assert enterprise_slug in {row.tenant_slug for row in rows}
        with pytest.raises(ApiError) as duplicate:
            await store.create_enterprise(
                actor=actor,
                body=body.model_copy(
                    update={"admin_account": f"other-{enterprise_slug}@example.test"}
                ),
                trace_id="platform-postgres-integration-duplicate",
            )
        assert duplicate.value.code == "TENANT_SLUG_CONFLICT"

        async with owner.connect() as connection:
            counts = (
                await connection.execute(
                    text(
                        "SELECT "
                        "(SELECT count(*) FROM cards WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM memberships WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM staff_credentials WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM outbox_events WHERE company_id=:company_id),"
                        "(SELECT count(*) FROM audit_logs WHERE company_id=:company_id)"
                    ),
                    {"company_id": created.company_id},
                )
            ).one()
        assert tuple(counts) == (1, 1, 1, 1, 1)
    finally:
        await runtime.dispose()
        await owner.dispose()


@pytest.mark.asyncio
async def test_document_onboarding_uses_slug_for_provisional_rows_when_name_is_missing() -> None:
    settings = Settings()
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    runtime = create_async_engine(settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    (
        actor_tenant_id,
        actor_company_id,
        actor_user_id,
        membership_id,
        session_id,
        other_user_id,
        other_membership_id,
        other_session_id,
    ) = [
        uuid.uuid4() for _ in range(8)
    ]
    actor_slug = f"platform-onboarding-{uuid.uuid4().hex[:10]}"
    enterprise_slug = f"document-onboarding-{uuid.uuid4().hex[:10]}"
    try:
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO tenants(id,slug,name,type,status,settings) "
                    "VALUES (:id,:slug,'Platform Onboarding','chamber','active','{}')"
                ),
                {"id": actor_tenant_id, "slug": actor_slug},
            )
            await connection.execute(
                text(
                    "INSERT INTO companies(id,tenant_id,name,normalized_name,status,settings) "
                    "VALUES (:id,:tenant_id,'Platform Onboarding',"
                    "'platform onboarding','active','{}')"
                ),
                {"id": actor_company_id, "tenant_id": actor_tenant_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO users(id,display_name,status) "
                    "VALUES (:id,'Platform Onboarding','active')"
                ),
                {"id": actor_user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO memberships("
                    "id,user_id,tenant_id,company_id,role,permissions,status) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,'platform_admin',"
                    "ARRAY['*'],'active')"
                ),
                {
                    "id": membership_id,
                    "user_id": actor_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO auth_sessions(id,user_id,tenant_id,company_id,"
                    "refresh_token_hash,expires_at) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,:token_hash,:expires_at)"
                ),
                {
                    "id": session_id,
                    "user_id": actor_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                    "token_hash": uuid.uuid4().hex,
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO users(id,display_name,status) "
                    "VALUES (:id,'Other Platform Admin','active')"
                ),
                {"id": other_user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO memberships("
                    "id,user_id,tenant_id,company_id,role,permissions,status) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,'platform_admin',"
                    "ARRAY['*'],'active')"
                ),
                {
                    "id": other_membership_id,
                    "user_id": other_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO auth_sessions(id,user_id,tenant_id,company_id,"
                    "refresh_token_hash,expires_at) "
                    "VALUES (:id,:user_id,:tenant_id,:company_id,:token_hash,:expires_at)"
                ),
                {
                    "id": other_session_id,
                    "user_id": other_user_id,
                    "tenant_id": actor_tenant_id,
                    "company_id": actor_company_id,
                    "token_hash": uuid.uuid4().hex,
                    "expires_at": datetime.now(UTC) + timedelta(hours=1),
                },
            )

        actor = PlatformActor(
            user_id=actor_user_id,
            tenant_id=actor_tenant_id,
            company_id=actor_company_id,
            session_id=session_id,
            role="platform_admin",
        )
        other_actor = PlatformActor(
            user_id=other_user_id,
            tenant_id=actor_tenant_id,
            company_id=actor_company_id,
            session_id=other_session_id,
            role="platform_admin",
        )
        service = PlatformOnboardingService(sessions, settings)
        created = await service.start(
            actor=actor,
            body=StartPlatformOnboardingRequest(
                tenant_slug=enterprise_slug,
                tenant_name=None,
                admin_account=f"{enterprise_slug}@example.test",
                admin_display_name="Document Onboarding Admin",
                admin_password=SecretStr("Document-Onboarding-2026!"),
            ),
            trace_id="platform-document-onboarding-integration",
        )
        assert created.tenant_name is None
        assert created.admin_account == f"{enterprise_slug}@example.test"
        assert created.admin_display_name == "Document Onboarding Admin"
        assert created.initial_card_display_name == enterprise_slug
        assert created.initial_card_title == enterprise_slug
        assert "admin_password" not in created.model_dump(mode="json")

        other_rows, other_total = await service.list_sessions(
            actor=other_actor,
            limit=100,
            offset=0,
        )
        assert other_total == 0
        assert other_rows == []
        for operation in (
            service.get_session,
            service.import_scope,
            service.get_import_status,
        ):
            with pytest.raises(ApiError) as hidden:
                await operation(actor=other_actor, onboarding_id=created.id)
            assert hidden.value.status_code == 404
            assert hidden.value.code == "RESOURCE_NOT_FOUND"
        with pytest.raises(ApiError) as hidden_confirm:
            await service.confirm(
                actor=other_actor,
                onboarding_id=created.id,
                body=ConfirmPlatformOnboardingRequest(
                    expected_version=created.version,
                    tenant_name="Must Stay Hidden",
                    company_name="Must Stay Hidden",
                    initial_card_display_name="Must Stay Hidden",
                ),
                trace_id="platform-document-onboarding-cross-owner-confirm",
            )
        assert hidden_confirm.value.status_code == 404
        assert hidden_confirm.value.code == "RESOURCE_NOT_FOUND"

        target = await service.import_scope(actor=actor, onboarding_id=created.id)
        batch = await KnowledgeImportStore(sessions, settings).create_batch(
            scope=target.scope,
            items=[
                PendingImport(
                    file_name="company.txt",
                    source_type="txt",
                    content_type="text/plain",
                    payload="企业资料".encode(),
                )
            ],
            auto_publish=False,
            trace_id="platform-document-onboarding-import",
        )
        attached = await service.attach_import_batch(
            actor=actor,
            onboarding_id=created.id,
            batch_id=batch.id,
            expected_version=target.version,
            trace_id="platform-document-onboarding-attach",
        )
        progress = await service.get_import_status(
            actor=actor,
            onboarding_id=created.id,
        )
        assert progress.settled is False
        assert [value.id for value in progress.batches] == [batch.id]
        assert [value.file_name for value in progress.batches[0].items] == ["company.txt"]

        cancelled = await service.cancel(
            actor=actor,
            onboarding_id=created.id,
            expected_version=attached.version,
            reason="security terminal redaction check",
            trace_id="platform-document-onboarding-cancel",
        )
        assert cancelled.status == "cancelled"
        assert cancelled.admin_account is None
        assert cancelled.admin_display_name is None
        assert cancelled.initial_card_display_name is None
        assert cancelled.initial_card_title is None
        with pytest.raises(ApiError) as closed_imports:
            await service.get_import_status(actor=actor, onboarding_id=created.id)
        assert closed_imports.value.status_code == 409
        assert closed_imports.value.code == "ONBOARDING_SESSION_CLOSED"

        confirm_slug = f"confirm-{uuid.uuid4().hex[:12]}"
        confirm_started = await service.start(
            actor=actor,
            body=StartPlatformOnboardingRequest(
                tenant_slug=confirm_slug,
                tenant_name="Confirmed Enterprise",
                admin_account=f"{confirm_slug}@example.test",
                admin_display_name="Confirmed Enterprise Admin",
                admin_password=SecretStr("Confirmed-Enterprise-2026!"),
            ),
            trace_id="platform-document-onboarding-confirm-start",
        )
        confirm_body = ConfirmPlatformOnboardingRequest(
            expected_version=confirm_started.version,
            tenant_name="Confirmed Enterprise",
            company_name="Confirmed Enterprise Co",
            initial_card_display_name="Confirmed Enterprise",
            initial_card_title="Confirmed Enterprise Official Card",
        )
        confirmed = await service.confirm(
            actor=actor,
            onboarding_id=confirm_started.id,
            body=confirm_body,
            trace_id="platform-document-onboarding-confirm",
        )
        confirmed_again = await service.confirm(
            actor=actor,
            onboarding_id=confirm_started.id,
            body=confirm_body,
            trace_id="platform-document-onboarding-confirm-retry",
        )
        assert confirmed_again == confirmed
        assert confirmed.status == "confirmed"
        assert confirmed.admin_account is None
        with pytest.raises(ApiError) as hidden_confirmed:
            await service.confirm(
                actor=other_actor,
                onboarding_id=confirm_started.id,
                body=confirm_body,
                trace_id="platform-document-onboarding-cross-owner-confirmed",
            )
        assert hidden_confirmed.value.status_code == 404
        assert hidden_confirmed.value.code == "RESOURCE_NOT_FOUND"

        resource_state = text(
            "SELECT tenant.name AS tenant_name, company.name AS company_name, "
            "card.display_name, card.settings ->> 'title' AS card_title, "
            "tenant.status::text AS tenant_status, "
            "company.status::text AS company_status, "
            "member.status::text AS membership_status, "
            "usr.status::text AS user_status, card.status::text AS card_status, "
            "credential.is_enabled "
            "FROM platform_onboarding_sessions AS onboarding "
            "JOIN tenants AS tenant ON tenant.id=onboarding.tenant_id "
            "JOIN companies AS company ON company.id=onboarding.company_id "
            "JOIN cards AS card ON card.id=onboarding.initial_card_id "
            "JOIN memberships AS member ON member.id=onboarding.admin_membership_id "
            "JOIN users AS usr ON usr.id=onboarding.admin_user_id "
            "JOIN staff_credentials AS credential "
            "ON credential.id=onboarding.credential_id "
            "WHERE onboarding.id=:onboarding_id"
        )
        ai_configuration_state = text(
            "SELECT prompt.name AS prompt_name, prompt.status::text AS prompt_status, "
            "model.provider, model.model_name, model.enabled "
            "FROM platform_onboarding_sessions AS onboarding "
            "JOIN prompt_versions AS prompt "
            "ON prompt.tenant_id=onboarding.tenant_id "
            "AND prompt.company_id=onboarding.company_id "
            "AND prompt.purpose='rag_answer' "
            "JOIN model_configs AS model "
            "ON model.tenant_id=onboarding.tenant_id "
            "AND model.company_id=onboarding.company_id "
            "AND model.purpose='chat' "
            "WHERE onboarding.id=:onboarding_id"
        )
        async with owner.connect() as connection:
            provisional_row = (
                await connection.execute(
                    resource_state,
                    {"onboarding_id": created.id},
                )
            ).one()
            confirmed_row = (
                await connection.execute(
                    resource_state,
                    {"onboarding_id": confirm_started.id},
                )
            ).one()
            confirmed_ai = (
                await connection.execute(
                    ai_configuration_state,
                    {"onboarding_id": confirm_started.id},
                )
            ).one()
        assert (
            provisional_row.tenant_name,
            provisional_row.company_name,
            provisional_row.display_name,
            provisional_row.card_title,
        ) == (enterprise_slug,) * 4
        assert (
            provisional_row.tenant_status,
            provisional_row.company_status,
            provisional_row.membership_status,
            provisional_row.user_status,
            provisional_row.card_status,
            provisional_row.is_enabled,
        ) == ("suspended", "suspended", "suspended", "suspended", "draft", False)
        assert (
            confirmed_row.tenant_name,
            confirmed_row.company_name,
            confirmed_row.display_name,
            confirmed_row.card_title,
        ) == (
            "Confirmed Enterprise",
            "Confirmed Enterprise Co",
            "Confirmed Enterprise",
            "Confirmed Enterprise Official Card",
        )
        assert (
            confirmed_row.tenant_status,
            confirmed_row.company_status,
            confirmed_row.membership_status,
            confirmed_row.user_status,
            confirmed_row.card_status,
            confirmed_row.is_enabled,
        ) == ("active", "active", "active", "active", "draft", True)
        assert (
            confirmed_ai.prompt_name,
            confirmed_ai.prompt_status,
            confirmed_ai.provider,
            confirmed_ai.model_name,
            confirmed_ai.enabled,
        ) == (
            DEFAULT_PROMPT_VERSION,
            "published",
            settings.llm_provider,
            settings.llm_model,
            True,
        )
    finally:
        await runtime.dispose()
        await owner.dispose()
