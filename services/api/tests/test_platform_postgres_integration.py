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
    PlatformOnboardingCandidateSelection,
    StartPlatformOnboardingRequest,
)
from app.core.config import Settings
from app.services.admin_store import AdminStore
from app.services.auth_store import AuthStore
from app.services.catalog_store import CatalogStore
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
    ) = [uuid.uuid4() for _ in range(8)]
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
        admin_store = AdminStore(sessions, settings)
        catalog_store = CatalogStore(sessions)
        created = await service.start(
            actor=actor,
            body=StartPlatformOnboardingRequest(
                tenant_slug=enterprise_slug,
                tenant_name=None,
                admin_account=f"{enterprise_slug}@example.test",
                admin_display_name="Document Onboarding Admin",
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
                admin=admin_store,
                catalog=catalog_store,
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
            display_name=None,
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

        review_run_id = uuid.uuid4()
        review_candidate_id = uuid.uuid4()
        async with owner.begin() as connection:
            onboarding_scope = (
                await connection.execute(
                    text(
                        "SELECT tenant_id, company_id, admin_user_id "
                        "FROM platform_onboarding_sessions WHERE id=:onboarding_id"
                    ),
                    {"onboarding_id": created.id},
                )
            ).one()
            await connection.execute(
                text(
                    "INSERT INTO content_import_runs("
                    "id,tenant_id,company_id,batch_id,requested_by,status,provider,model,"
                    "attempts,counts,completed_at) VALUES ("
                    ":id,:tenant_id,:company_id,:batch_id,:requested_by,'review',"
                    "'integration','review-v1',1,"
                    "CAST(:counts AS jsonb),clock_timestamp())"
                ),
                {
                    "id": review_run_id,
                    "tenant_id": onboarding_scope.tenant_id,
                    "company_id": onboarding_scope.company_id,
                    "batch_id": batch.id,
                    "requested_by": onboarding_scope.admin_user_id,
                    "counts": '{"accepted":1}',
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO content_import_candidates("
                    "id,tenant_id,company_id,run_id,category,payload,source_id,"
                    "source_text,confidence,fingerprint,status,target_resource_type,"
                    "target_resource_id,reviewed_by,reviewed_at,version) VALUES ("
                    ":id,:tenant_id,:company_id,:run_id,'products',CAST(:payload AS jsonb),"
                    "'source-accepted',"
                    "'accepted evidence',0.9,repeat('a',64),'accepted','product',"
                    ":target_id,:reviewed_by,clock_timestamp(),2)"
                ),
                {
                    "id": review_candidate_id,
                    "tenant_id": onboarding_scope.tenant_id,
                    "company_id": onboarding_scope.company_id,
                    "run_id": review_run_id,
                    "payload": '{"name":"Accepted product"}',
                    "target_id": uuid.uuid4(),
                    "reviewed_by": onboarding_scope.admin_user_id,
                },
            )
        reopened = await service.get_session(actor=actor, onboarding_id=created.id)
        assert reopened.content_review is not None
        assert reopened.content_review.id == review_run_id
        assert reopened.content_review.candidates[0].status == "accepted"
        listed_rows, _ = await service.list_sessions(actor=actor, limit=100, offset=0)
        listed_reopened = next(row for row in listed_rows if row.id == created.id)
        assert listed_reopened.content_review is not None
        assert listed_reopened.content_review.id == review_run_id
        assert listed_reopened.content_review.counts == {"accepted": 1}

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
            ),
            trace_id="platform-document-onboarding-confirm-start",
        )
        confirm_target = await service.import_scope(
            actor=actor,
            onboarding_id=confirm_started.id,
        )
        confirm_batch = await KnowledgeImportStore(sessions, settings).create_batch(
            scope=confirm_target.scope,
            items=[
                PendingImport(
                    file_name="confirmed-company.txt",
                    source_type="txt",
                    content_type="text/plain",
                    payload="待确认产品资料".encode(),
                )
            ],
            auto_publish=False,
            display_name=None,
            trace_id="platform-document-onboarding-confirm-import",
        )
        confirm_attached = await service.attach_import_batch(
            actor=actor,
            onboarding_id=confirm_started.id,
            batch_id=confirm_batch.id,
            expected_version=confirm_target.version,
            trace_id="platform-document-onboarding-confirm-attach",
        )
        selected_run_id = uuid.uuid4()
        selected_candidate_id = uuid.uuid4()
        selected_faq_candidate_id = uuid.uuid4()
        async with owner.begin() as connection:
            confirm_scope = (
                await connection.execute(
                    text(
                        "SELECT tenant_id, company_id, admin_user_id "
                        "FROM platform_onboarding_sessions WHERE id=:onboarding_id"
                    ),
                    {"onboarding_id": confirm_started.id},
                )
            ).one()
            await connection.execute(
                text(
                    "UPDATE knowledge_import_items SET status='completed' WHERE batch_id=:batch_id"
                ),
                {"batch_id": confirm_batch.id},
            )
            await connection.execute(
                text("UPDATE knowledge_import_batches SET status='completed' WHERE id=:batch_id"),
                {"batch_id": confirm_batch.id},
            )
            await connection.execute(
                text(
                    "INSERT INTO content_import_runs("
                    "id,tenant_id,company_id,batch_id,requested_by,status,provider,model,"
                    "attempts,counts,completed_at) VALUES ("
                    ":id,:tenant_id,:company_id,:batch_id,:requested_by,'review',"
                    "'integration','review-v1',1,CAST(:counts AS jsonb),clock_timestamp())"
                ),
                {
                    "id": selected_run_id,
                    "tenant_id": confirm_scope.tenant_id,
                    "company_id": confirm_scope.company_id,
                    "batch_id": confirm_batch.id,
                    "requested_by": confirm_scope.admin_user_id,
                    "counts": '{"pending_review":2}',
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO content_import_candidates("
                    "id,tenant_id,company_id,run_id,category,payload,source_id,"
                    "source_text,confidence,fingerprint,status,version) VALUES ("
                    ":id,:tenant_id,:company_id,:run_id,'products',"
                    "CAST(:payload AS jsonb),'selected-product','selected evidence',"
                    "0.95,repeat('b',64),'pending_review',1)"
                ),
                {
                    "id": selected_candidate_id,
                    "tenant_id": confirm_scope.tenant_id,
                    "company_id": confirm_scope.company_id,
                    "run_id": selected_run_id,
                    "payload": (
                        '{"name":"Imported Product","category":"Service",'
                        '"summary":"Imported summary","detail":"Imported detail",'
                        '"audience":"Enterprise","price_boundary":null}'
                    ),
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO content_import_candidates("
                    "id,tenant_id,company_id,run_id,category,payload,source_id,"
                    "source_text,confidence,fingerprint,status,version) VALUES ("
                    ":id,:tenant_id,:company_id,:run_id,'faqs',"
                    "CAST(:payload AS jsonb),'selected-faq','selected FAQ evidence',"
                    "0.9,repeat('c',64),'pending_review',1)"
                ),
                {
                    "id": selected_faq_candidate_id,
                    "tenant_id": confirm_scope.tenant_id,
                    "company_id": confirm_scope.company_id,
                    "run_id": selected_run_id,
                    "payload": '{"question":"Imported FAQ?","answer":"Imported answer."}',
                },
            )
        failed_confirm_body = ConfirmPlatformOnboardingRequest(
            expected_version=confirm_attached.version,
            tenant_name="Confirmed Enterprise",
            company_name="Confirmed Enterprise Co",
            initial_card_display_name="Confirmed Enterprise",
            initial_card_title="Confirmed Enterprise Official Card",
            candidate_selections=[
                PlatformOnboardingCandidateSelection(
                    id=selected_candidate_id,
                    expected_version=1,
                    apply_fields=[],
                ),
                PlatformOnboardingCandidateSelection(
                    id=selected_faq_candidate_id,
                    expected_version=2,
                    apply_fields=[],
                ),
            ],
        )
        with pytest.raises(ApiError) as selected_failure:
            await service.confirm(
                actor=actor,
                onboarding_id=confirm_started.id,
                body=failed_confirm_body,
                admin=admin_store,
                catalog=catalog_store,
                trace_id="platform-document-onboarding-confirm-partial-failure",
            )
        assert selected_failure.value.code == "VERSION_CONFLICT"
        async with owner.connect() as connection:
            provisional_after_failure = (
                await connection.execute(
                    text(
                        "SELECT status, confirmed_at FROM platform_onboarding_sessions "
                        "WHERE id=:onboarding_id"
                    ),
                    {"onboarding_id": confirm_started.id},
                )
            ).one()
            product_count_after_failure = await connection.scalar(
                text(
                    "SELECT count(*) FROM products "
                    "WHERE company_id=:company_id "
                    "AND settings ->> 'content_import_candidate_id'=:candidate_id"
                ),
                {
                    "company_id": confirm_scope.company_id,
                    "candidate_id": str(selected_candidate_id),
                },
            )
        assert provisional_after_failure.status != "confirmed"
        assert provisional_after_failure.confirmed_at is None
        assert product_count_after_failure == 1
        confirm_body = ConfirmPlatformOnboardingRequest(
            expected_version=confirm_attached.version,
            tenant_name="Confirmed Enterprise",
            company_name="Confirmed Enterprise Co",
            initial_card_display_name="Confirmed Enterprise",
            initial_card_title="Confirmed Enterprise Official Card",
            candidate_selections=[
                PlatformOnboardingCandidateSelection(
                    id=selected_candidate_id,
                    expected_version=1,
                    apply_fields=[],
                ),
                PlatformOnboardingCandidateSelection(
                    id=selected_faq_candidate_id,
                    expected_version=1,
                    apply_fields=[],
                ),
            ],
        )
        confirmed = await service.confirm(
            actor=actor,
            onboarding_id=confirm_started.id,
            body=confirm_body,
            admin=admin_store,
            catalog=catalog_store,
            trace_id="platform-document-onboarding-confirm",
        )
        confirmed_again = await service.confirm(
            actor=actor,
            onboarding_id=confirm_started.id,
            body=confirm_body,
            admin=admin_store,
            catalog=catalog_store,
            trace_id="platform-document-onboarding-confirm-retry",
        )
        assert confirmed_again.id == confirmed.id
        assert confirmed_again.status == confirmed.status
        assert confirmed_again.version == confirmed.version
        assert confirmed.credential_delivery is not None
        assert confirmed_again.credential_delivery is None
        assert confirmed.status == "confirmed"
        assert confirmed.admin_account == f"{confirm_slug}@example.test"
        assert confirmed.temporary_credential_reset_available is True
        assert confirmed.content_review is not None
        assert confirmed.content_review.id == selected_run_id
        assert {candidate.status for candidate in confirmed.content_review.candidates} == {
            "accepted"
        }
        assert confirmed.credential_delivery is not None
        first_temporary_password = confirmed.credential_delivery.temporary_password
        regenerated = await service.regenerate_temporary_credential(
            actor=actor,
            onboarding_id=confirmed.id,
            expected_version=confirmed.version,
            trace_id="platform-document-onboarding-credential-regenerate",
        )
        assert regenerated.version == confirmed.version + 1
        assert regenerated.credential_delivery is not None
        regenerated_password = regenerated.credential_delivery.temporary_password
        assert regenerated_password != first_temporary_password
        assert regenerated.credential_delivery.expires_at > datetime.now(UTC) + timedelta(days=6)
        auth_store = AuthStore(sessions, settings)
        with pytest.raises(ApiError) as invalidated_password:
            await auth_store.login(
                account=f"{confirm_slug}@example.test",
                credential=first_temporary_password,
            )
        assert invalidated_password.value.code == "INVALID_CREDENTIALS"
        authentication = await auth_store.login(
            account=f"{confirm_slug}@example.test",
            credential=regenerated_password,
        )
        assert authentication.identity.must_change_password is True
        with pytest.raises(ApiError) as stale_regenerate:
            await service.regenerate_temporary_credential(
                actor=actor,
                onboarding_id=confirmed.id,
                expected_version=confirmed.version,
                trace_id="platform-document-onboarding-credential-stale",
            )
        assert stale_regenerate.value.code == "ONBOARDING_VERSION_CONFLICT"
        with pytest.raises(ApiError) as hidden_confirmed:
            await service.confirm(
                actor=other_actor,
                onboarding_id=confirm_started.id,
                body=confirm_body,
                admin=admin_store,
                catalog=catalog_store,
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
            accepted_product_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM products "
                    "WHERE company_id=:company_id "
                    "AND settings ->> 'content_import_candidate_id'=:candidate_id "
                    "AND status='draft'"
                ),
                {
                    "company_id": confirm_scope.company_id,
                    "candidate_id": str(selected_candidate_id),
                },
            )
            accepted_faq_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM knowledge_documents "
                    "WHERE company_id=:company_id AND source_type='faq' "
                    "AND source_id=:source_id AND status='draft'"
                ),
                {
                    "company_id": confirm_scope.company_id,
                    "source_id": f"content-import:{selected_faq_candidate_id}",
                },
            )
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
        assert accepted_product_count == 1
        assert accepted_faq_count == 1

        # The worker beat projects an untouched overdue open session to
        # ``expired`` before applying its separate 30-day cleanup window.
        expiry_slug = f"expiry-{uuid.uuid4().hex[:12]}"
        expiry_started = await service.start(
            actor=actor,
            body=StartPlatformOnboardingRequest(
                tenant_slug=expiry_slug,
                tenant_name="Expiry Projection Enterprise",
                admin_account=f"{expiry_slug}@example.test",
                admin_display_name="Expiry Projection Admin",
            ),
            trace_id="platform-document-onboarding-expiry-start",
        )
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform_onboarding_sessions "
                    "SET expires_at=clock_timestamp() - interval '1 minute' "
                    "WHERE id=:onboarding_id"
                ),
                {"onboarding_id": expiry_started.id},
            )
            processed = await connection.scalar(
                text("SELECT app.purge_expired_platform_onboarding_sessions()")
            )
            expiry_state = (
                await connection.execute(
                    text(
                        "SELECT status, retention_cleanup_after, purged_at "
                        "FROM platform_onboarding_sessions WHERE id=:onboarding_id"
                    ),
                    {"onboarding_id": expiry_started.id},
                )
            ).one()
            worker_can_execute = await connection.scalar(
                text(
                    "SELECT has_function_privilege("
                    "'cf_ai_card_worker', "
                    "'app.purge_expired_platform_onboarding_sessions()', "
                    "'EXECUTE')"
                )
            )
        assert processed == 1
        assert expiry_state.status == "expired"
        assert expiry_state.retention_cleanup_after > datetime.now(UTC) + timedelta(days=29)
        assert expiry_state.purged_at is None
        assert worker_can_execute is True

        # Terminal provisional sessions are scrubbed after retention. A
        # confirmed session remains hard-excluded even if metadata is tampered
        # to look cleanup-eligible.
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE platform_onboarding_sessions "
                    "SET retention_cleanup_after=clock_timestamp() - interval '1 minute' "
                    "WHERE id IN (:cancelled_id, :expired_id, :confirmed_id)"
                ),
                {
                    "cancelled_id": created.id,
                    "expired_id": expiry_started.id,
                    "confirmed_id": confirmed.id,
                },
            )
            cleaned = await connection.scalar(
                text("SELECT app.purge_expired_platform_onboarding_sessions()")
            )
            cleanup_rows = (
                await connection.execute(
                    text(
                        "SELECT id, status, purged_at, purge_summary "
                        "FROM platform_onboarding_sessions "
                        "WHERE id IN (:cancelled_id, :expired_id, :confirmed_id)"
                    ),
                    {
                        "cancelled_id": created.id,
                        "expired_id": expiry_started.id,
                        "confirmed_id": confirmed.id,
                    },
                )
            ).all()
            remaining_imports = await connection.scalar(
                text("SELECT count(*) FROM knowledge_import_batches WHERE id=:batch_id"),
                {"batch_id": batch.id},
            )
        cleanup_by_id = {row.id: row for row in cleanup_rows}
        assert cleaned == 2
        assert cleanup_by_id[created.id].purged_at is not None
        assert cleanup_by_id[expiry_started.id].purged_at is not None
        assert (
            cleanup_by_id[created.id].purge_summary["core_resource_disposition"]
            == "scrubbed_and_soft_deleted"
        )
        assert cleanup_by_id[confirmed.id].status == "confirmed"
        assert cleanup_by_id[confirmed.id].purged_at is None
        assert remaining_imports == 0
    finally:
        await runtime.dispose()
        await owner.dispose()
