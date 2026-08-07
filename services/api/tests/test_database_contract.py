from __future__ import annotations

import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import ForeignKeyConstraint

from app.db.base import Base
from app.db.models import EMBEDDING_DIMENSION

API_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_ROOT / "alembic.ini"
MIGRATIONS = API_ROOT / "migrations"

REQUIRED_TABLES = {
    "tenants",
    "companies",
    "users",
    "memberships",
    "auth_sessions",
    "staff_credentials",
    "security_events",
    "cards",
    "card_contact_fields",
    "products",
    "case_studies",
    "forbidden_topics",
    "visitors",
    "visitor_profiles",
    "consent_records",
    "visits",
    "visit_events",
    "conversations",
    "messages",
    "ai_runs",
    "message_citations",
    "knowledge_documents",
    "knowledge_versions",
    "knowledge_chunks",
    "knowledge_index_jobs",
    "knowledge_gaps",
    "visit_summaries",
    "leads",
    "lead_followups",
    "privacy_requests",
    "notifications",
    "prompt_versions",
    "model_configs",
    "idempotency_keys",
    "audit_logs",
    "outbox_events",
    "outbox_deliveries",
    "worker_job_results",
    "data_export_requests",
    "visitor_profile_signals",
    "visitor_profile_signal_sources",
    "knowledge_import_batches",
    "knowledge_import_items",
    "wecom_user_bindings",
    "wecom_enterprise_scopes",
    "wecom_callback_events",
}

COMPANY_SCOPED_TABLES = REQUIRED_TABLES - {
    "tenants",
    "companies",
    "users",
    "memberships",
    "auth_sessions",
    "staff_credentials",
    "security_events",
    "wecom_enterprise_scopes",
}


@pytest.fixture(scope="module")
def migration_sql() -> str:
    """Render the complete migration using PostgreSQL's offline dialect.

    Alembic compiles every operation, model imports are exercised, and no
    database connection is opened.
    """

    output = StringIO()
    config = Config(str(ALEMBIC_INI), output_buffer=output)
    config.set_main_option("script_location", str(MIGRATIONS))
    offline_url = "postgresql+asyncpg://contract:contract@localhost/contract"
    with patch.dict(os.environ, {"DATABASE_URL": offline_url}):
        command.upgrade(config, "head", sql=True)
    return " ".join(output.getvalue().lower().split())


def test_model_metadata_covers_database_core() -> None:
    assert REQUIRED_TABLES <= set(Base.metadata.tables)


def test_cards_distinguish_enterprise_and_employee_ownership(
    migration_sql: str,
) -> None:
    cards = Base.metadata.tables["cards"]
    assert cards.c.card_kind.nullable is False
    assert cards.c.owner_user_id.nullable is True
    assert cards.c.responsible_user_id.nullable is False
    assert any(
        constraint.name == "ck_cards_kind_owner_consistent"
        for constraint in cards.constraints
    )
    assert "add column card_kind" in migration_sql
    assert "add column responsible_user_id" in migration_sql
    assert "ck_cards_kind_owner_consistent" in migration_sql
    assert "platform_onboarding_sessions as onboarding" in migration_sql


def test_company_owned_models_always_carry_both_scope_columns() -> None:
    for table_name in COMPANY_SCOPED_TABLES:
        columns = set(Base.metadata.tables[table_name].columns.keys())
        assert {"tenant_id", "company_id"} <= columns, table_name


def test_cross_resource_links_use_composite_scope_foreign_keys() -> None:
    for table_name in COMPANY_SCOPED_TABLES:
        table = Base.metadata.tables[table_name]
        scoped_fks = [
            constraint
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint)
            and {"tenant_id", "company_id"} <= {column.name for column in constraint.columns}
        ]
        assert scoped_fks, f"{table_name} lacks a tenant/company composite FK"


def test_hybrid_knowledge_chunk_model_contract() -> None:
    chunk = Base.metadata.tables["knowledge_chunks"]
    assert {"document_id", "version_id", "ordinal", "search_tsv"} <= set(chunk.columns.keys())
    assert EMBEDDING_DIMENSION == 1024
    assert chunk.c.embedding.type.dim == 1024
    assert chunk.c.embedding.nullable
    assert chunk.c.embedding_model.nullable
    assert chunk.c.search_tsv.computed is not None
    assert chunk.c.search_tsv.computed.persisted is True


def test_offline_migration_creates_required_extensions_and_tables(migration_sql: str) -> None:
    for extension in ("pgcrypto", "vector", "pg_trgm"):
        assert f"create extension if not exists {extension}" in migration_sql
    for table_name in REQUIRED_TABLES:
        assert f"create table {table_name}" in migration_sql


def test_platform_function_expression_repair_is_part_of_current_head(
    migration_sql: str,
) -> None:
    assert "repair_platform_functions" in migration_sql
    assert "pg_catalog.pg_get_functiondef" in migration_sql
    assert "platform function expression repair was incomplete" in migration_sql


def test_offline_migration_freezes_hybrid_retrieval_contract(migration_sql: str) -> None:
    assert "embedding vector(1024)" in migration_sql
    assert "search_tsv tsvector generated always as" in migration_sql
    assert "using hnsw(embedding vector_cosine_ops)" in migration_sql
    assert "where embedding is not null" in migration_sql
    assert "using gin(search_tsv)" in migration_sql
    assert "gin_trgm_ops" in migration_sql


def test_rls_is_enabled_and_forced_for_every_company_table(migration_sql: str) -> None:
    for table_name in COMPANY_SCOPED_TABLES:
        assert f"alter table {table_name} enable row level security" in migration_sql
        assert f"alter table {table_name} force row level security" in migration_sql
        assert f"create policy {table_name}_scope_isolation on {table_name}" in migration_sql
    assert "app.scope_matches(tenant_id, company_id)" in migration_sql


def test_public_card_policy_is_exact_slug_scope(migration_sql: str) -> None:
    assert "slug ~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'" in migration_sql
    assert "create policy cards_public_slug_select on cards for select" in migration_sql
    assert "slug = app.current_card_slug()" in migration_sql
    public_policy = migration_sql.split("create policy cards_public_slug_select", 1)[1]
    public_policy = public_policy.split(";", 1)[0]
    assert " like " not in public_policy
    assert "status = 'published'" in public_policy


def test_staff_login_boundary_is_unscoped_but_binds_an_exact_company(migration_sql: str) -> None:
    credential = Base.metadata.tables["staff_credentials"]
    assert {
        "user_id",
        "membership_id",
        "tenant_id",
        "company_id",
        "account_normalized",
        "password_hash",
        "failed_attempts",
        "locked_until",
    } <= set(credential.columns.keys())
    assert "create table staff_credentials" in migration_sql
    assert "uq_staff_credentials_account" in migration_sql
    assert "foreign key(tenant_id, company_id)" in migration_sql
    assert "references companies (tenant_id, id)" in migration_sql
    assert "alter table staff_credentials enable row level security" not in migration_sql
    assert "alter table memberships force row level security" in migration_sql
    assert "alter table auth_sessions force row level security" in migration_sql


def test_wecom_first_login_bootstrap_uses_narrow_security_definer_boundary(
    migration_sql: str,
) -> None:
    scope = Base.metadata.tables["wecom_enterprise_scopes"]
    assert {"corp_id_hmac", "tenant_id", "company_id"} <= set(scope.columns.keys())
    assert "create function app.resolve_wecom_identity" in migration_sql
    assert "create function app.bootstrap_wecom_enterprise" in migration_sql
    assert "security definer" in migration_sql
    assert "revoke all on table wecom_enterprise_scopes from public" in migration_sql
    assert "grant execute on function app.bootstrap_wecom_enterprise" in migration_sql
    assert "grant select" not in migration_sql.split(
        "create table wecom_enterprise_scopes", 1
    )[1].split("create function app.resolve_wecom_identity", 1)[0]


def test_active_document_requires_its_own_approved_version(migration_sql: str) -> None:
    assert "foreign key (tenant_id, company_id, id, current_version_id)" in migration_sql
    assert "references knowledge_versions(tenant_id, company_id, document_id, id)" in migration_sql
    assert "published document requires its own approved version" in migration_sql
    assert "selected_review_status is distinct from 'approved'" in migration_sql
    assert "new.status = 'published'" in migration_sql


def test_immutable_knowledge_and_append_only_audit_guards(migration_sql: str) -> None:
    assert "create trigger trg_knowledge_versions_immutable" in migration_sql
    assert "create trigger trg_knowledge_chunks_immutable" in migration_sql
    assert "new_row := to_jsonb(new)" in migration_sql
    assert "old_row := to_jsonb(old)" in migration_sql
    assert "knowledge version content is immutable" in migration_sql
    assert "active knowledge chunk embedding is immutable" in migration_sql
    assert "create trigger trg_audit_logs_append_only" in migration_sql
    assert "audit logs are append-only" in migration_sql
    assert "create function app.erase_visitor_lead_followups" in migration_sql
    assert "security definer" in migration_sql
    assert "encryption_key_ref = 'erased'" in migration_sql
    assert (
        "revoke all privileges on table lead_followups, security_events from cf_ai_card_app"
        in migration_sql
    )
    assert "alter default privileges in schema public" in migration_sql
    assert "revoke all on tables from cf_ai_card_app" in migration_sql
    assert "lead_followups to cf_ai_card_app" in migration_sql
    assert (
        "lead_followups"
        not in migration_sql.split("grant select, insert, update, delete on table", 1)[1].split(
            "to cf_ai_card_app", 1
        )[0]
    )


def test_security_events_are_unscoped_and_write_only_for_runtime(migration_sql: str) -> None:
    security_event = Base.metadata.tables["security_events"]
    assert {"event_type", "outcome", "account_hash", "request_ip_hash"} <= set(
        security_event.columns.keys()
    )
    assert "alter table security_events enable row level security" not in migration_sql
    assert "grant insert on table security_events to cf_ai_card_app" in migration_sql


def test_published_catalog_records_require_a_publish_timestamp(migration_sql: str) -> None:
    assert "ck_products_published_requires_timestamp" in migration_sql
    assert "ck_case_studies_published_requires_timestamp" in migration_sql


def test_reliability_tables_have_deduplication_contracts(migration_sql: str) -> None:
    assert "uq_idempotency_keys_scope_key" in migration_sql
    assert "uq_outbox_events_deduplication_key" in migration_sql
    assert "ck_outbox_events_published_state" in migration_sql
    assert "entry_hash varchar(64) not null" in migration_sql
    assert "ck_outbox_events_processing_lease" in migration_sql
    assert "uq_outbox_deliveries_event_handler" in migration_sql
    assert "uq_worker_job_results_event" in migration_sql
    assert "create function app.claim_outbox_events" in migration_sql
    assert "security definer" in migration_sql
    assert "for update skip locked" in migration_sql
    assert "cf_ai_card_worker" in migration_sql


def test_async_exports_are_scoped_encrypted_expiring_worker_artifacts(
    migration_sql: str,
) -> None:
    export = Base.metadata.tables["data_export_requests"]
    assert {
        "requested_by",
        "export_type",
        "status",
        "scope_kind",
        "file_ciphertext",
        "file_sha256",
        "expires_at",
    } <= set(export.columns.keys())
    assert "alter table data_export_requests force row level security" in migration_sql
    assert "create policy data_export_requests_scope_isolation" in migration_sql
    assert "app.scope_matches(tenant_id, company_id)" in migration_sql
    assert "file_ciphertext bytea" in migration_sql
    assert "grant select, update on data_export_requests to cf_ai_card_worker" in migration_sql
    assert "grant select on visitors, visitor_profiles, visits, leads, messages" in migration_sql
    assert "bypassrls" not in migration_sql.split("create table data_export_requests", 1)[1]


def test_long_term_profiles_are_scoped_encrypted_and_physically_purged(
    migration_sql: str,
) -> None:
    signals = Base.metadata.tables["visitor_profile_signals"]
    sources = Base.metadata.tables["visitor_profile_signal_sources"]
    assert {
        "label_ciphertext",
        "label_hmac",
        "retention_expires_at",
    } <= set(signals.columns.keys())
    assert {"consent_id", "summary_id", "message_id", "retention_expires_at"} <= set(
        sources.columns.keys()
    )
    for table_name in ("visitor_profile_signals", "visitor_profile_signal_sources"):
        assert f"alter table {table_name} force row level security" in migration_sql
        assert f"create policy {table_name}_scope_isolation" in migration_sql
    assert "create or replace function app.purge_expired_visitor_profiles()" in migration_sql
    assert "revoke all on function app.purge_expired_visitor_profiles()" in migration_sql
    purge_grant = migration_sql.split(
        "grant execute on function app.purge_expired_visitor_profiles()", 1
    )[1].split("end if", 1)[0]
    assert "to cf_ai_card_worker" in purge_grant
    assert "to cf_ai_card_app" not in purge_grant


def test_scheduled_publishing_is_scoped_leased_and_versioned(migration_sql: str) -> None:
    job = Base.metadata.tables["scheduled_publish_jobs"]
    assert {
        "resource_type",
        "resource_id",
        "target_version",
        "scheduled_at",
        "lock_token",
        "lease_expires_at",
        "version",
    } <= set(job.columns.keys())
    indexes = {index.name: index for index in job.indexes}
    active_resource = indexes["uq_scheduled_publish_jobs_active_resource"]
    assert active_resource.unique
    assert [column.name for column in active_resource.columns] == [
        "tenant_id",
        "company_id",
        "resource_type",
        "resource_id",
    ]
    assert str(active_resource.dialect_options["postgresql"]["where"]) == (
        "status IN ('pending', 'processing', 'failed')"
    )
    assert "alter table scheduled_publish_jobs force row level security" in migration_sql
    assert "create policy scheduled_publish_jobs_scope_isolation" in migration_sql
    assert "create function app.claim_scheduled_publish_jobs" in migration_sql
    assert "for update skip locked" in migration_sql


def test_knowledge_imports_are_encrypted_scoped_leased_and_draft_only(
    migration_sql: str,
) -> None:
    batch = Base.metadata.tables["knowledge_import_batches"]
    item = Base.metadata.tables["knowledge_import_items"]
    assert {"requested_by", "status", "total_items", "failed_items"} <= set(batch.columns.keys())
    assert {
        "payload_ciphertext",
        "payload_sha256",
        "lock_token",
        "lease_expires_at",
        "document_id",
        "version_id",
    } <= set(item.columns.keys())
    assert "alter table knowledge_import_batches force row level security" in migration_sql
    assert "alter table knowledge_import_items force row level security" in migration_sql
    assert "create function app.claim_knowledge_import_items" in migration_sql
    assert "for update skip locked" in migration_sql
    assert "grant execute on function" in migration_sql
    assert "to cf_ai_card_worker" in migration_sql
    assert "bypassrls" not in migration_sql


def test_visitor_profile_downgrade_removes_unsupported_consent_scope() -> None:
    migration = (
        (MIGRATIONS / "versions" / "20260711_0010_visitor_profile_personalization.py")
        .read_text(encoding="utf-8")
        .lower()
    )
    delete_position = migration.index(
        "delete from consent_records where scope = 'profile_personalization'"
    )
    old_constraint_position = migration.index(
        "check (scope in ('browse_notice', 'chat_notice', 'lead_contact'))"
    )
    assert delete_position < old_constraint_position


def test_ai_runs_support_auditable_non_message_workflows(migration_sql: str) -> None:
    ai_run = Base.metadata.tables["ai_runs"]
    assert {"purpose", "resource_type", "resource_id"} <= set(ai_run.columns.keys())
    assert ai_run.c.message_id.nullable
    assert "alter table ai_runs add column purpose" in migration_sql
    assert "ck_ai_runs_source_reference_required" in migration_sql
    assert "create index ix_ai_runs_resource" in migration_sql


def test_platform_onboarding_has_a_narrow_authenticated_rls_path(
    migration_sql: str,
) -> None:
    tenant = Base.metadata.tables["tenants"]
    assert {"slug", "name", "type", "status"} <= set(tenant.columns.keys())
    assert "ck_tenants_slug_format" in migration_sql
    assert "uq_tenants_slug" in migration_sql
    assert "create function app.platform_actor_allowed() returns boolean" in migration_sql
    assert "security definer" in migration_sql
    assert "set search_path = pg_catalog, public, app" in migration_sql
    assert "auth.id = nullif(current_setting('app.session_id', true), '')::uuid" in migration_sql
    assert "membership.role = 'platform_admin'" in migration_sql
    for table_name in ("tenants", "companies", "users", "memberships", "cards"):
        assert f"create policy {table_name}_platform_insert" in migration_sql


def test_wecom_identity_and_callbacks_are_encrypted_scoped_and_deduplicated(
    migration_sql: str,
) -> None:
    binding = Base.metadata.tables["wecom_user_bindings"]
    callback = Base.metadata.tables["wecom_callback_events"]
    assert {
        "wecom_user_id_ciphertext",
        "wecom_user_id_hmac",
        "profile_ciphertext",
        "encryption_key_ref",
    } <= set(binding.columns.keys())
    assert {
        "provider_event_key",
        "payload_ciphertext",
        "status",
        "received_at",
    } <= set(callback.columns.keys())
    for table_name in ("wecom_user_bindings", "wecom_callback_events"):
        assert f"alter table {table_name} force row level security" in migration_sql
        assert f"create policy {table_name}_scope_isolation" in migration_sql
    assert "uq_wecom_callback_events_provider_key" in migration_sql
    assert "grant select, insert, update on wecom_user_bindings" in migration_sql
