from __future__ import annotations

from pathlib import Path

from app.integrations.wecom import WeComProviderError

from cf_worker.repository import (
    calculate_backoff_seconds,
    is_invalid_wecom_recipient_error,
    should_dead_letter,
)

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / "services/api/migrations/versions/20260711_0007_worker_outbox.py"
SCHEDULED_MIGRATION = ROOT / "services/api/migrations/versions/20260712_0011_scheduled_publish.py"
IMPORT_MIGRATION = ROOT / "services/api/migrations/versions/20260712_0012_knowledge_imports.py"
ROLE_GRANT_MIGRATION = (
    ROOT / "services/api/migrations/versions/20260715_0015_repair_database_role_grants.py"
)
VISIT_NOTIFICATION_MIGRATION = (
    ROOT / "services/api/migrations/versions/20260818_0040_visit_notifications.py"
)
VISIT_ROLLOUT_GUARD_MIGRATION = (
    ROOT / "services/api/migrations/versions/20260818_0042_visit_notification_rollout_guard.py"
)


def test_backoff_is_exponential_and_capped() -> None:
    assert calculate_backoff_seconds(attempt=1, base_seconds=5, maximum_seconds=900) == 5
    assert calculate_backoff_seconds(attempt=2, base_seconds=5, maximum_seconds=900) == 10
    assert calculate_backoff_seconds(attempt=20, base_seconds=5, maximum_seconds=900) == 900


def test_dead_letter_policy_handles_permanent_and_exhausted_events() -> None:
    assert should_dead_letter(attempt=1, max_attempts=6, permanent=True)
    assert should_dead_letter(attempt=6, max_attempts=6, permanent=False)
    assert not should_dead_letter(attempt=5, max_attempts=6, permanent=False)


def test_wecom_invalid_or_out_of_scope_members_do_not_fail_in_app_delivery() -> None:
    assert is_invalid_wecom_recipient_error(WeComProviderError("WECOM_INVALID_RECIPIENT"))
    assert is_invalid_wecom_recipient_error(
        WeComProviderError("WECOM_PROVIDER_REJECTED", provider_code=81013)
    )
    assert not is_invalid_wecom_recipient_error(
        WeComProviderError("WECOM_PROVIDER_REJECTED", provider_code=60020)
    )


def test_migration_enforces_skip_locked_leases_rls_and_worker_identity() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "for update skip locked" in sql
    assert "lease_expires_at" in sql
    assert "lock_token" in sql
    assert "security definer" in sql
    assert "set search_path = pg_catalog, public, app" in sql
    assert "outbox_deliveries" in sql
    assert "worker_job_results" in sql
    assert "force row level security" in sql
    assert "cf_ai_card_worker" in sql
    assert "bypassrls" not in sql


def test_scheduled_publish_claim_is_leased_scoped_and_least_privilege() -> None:
    sql = SCHEDULED_MIGRATION.read_text(encoding="utf-8").lower()
    assert "for update skip locked" in sql
    assert "security definer" in sql
    assert "force row level security" in sql
    assert "scheduled_publish_jobs_scope_isolation" in sql
    assert "claim_scheduled_publish_jobs" in sql
    assert "cf_ai_card_worker" in sql
    assert "bypassrls" not in sql


def test_knowledge_import_claim_is_leased_scoped_and_least_privilege() -> None:
    sql = IMPORT_MIGRATION.read_text(encoding="utf-8").lower()
    assert "for update skip locked" in sql
    assert "security definer" in sql
    assert "force row level security" in sql
    assert "claim_knowledge_import_items" in sql
    assert "payload_ciphertext" in sql
    assert "cf_ai_card_worker" in sql
    assert "bypassrls" not in sql


def test_role_repair_migration_restores_app_and_worker_least_privileges() -> None:
    sql = ROLE_GRANT_MIGRATION.read_text(encoding="utf-8").lower()
    assert "grant usage on schema public, app to cf_ai_card_app" in sql
    assert "grant usage on schema public, app to cf_ai_card_worker" in sql
    assert "app.claim_outbox_events(text, integer, integer)" in sql
    assert "app.claim_knowledge_import_items(text, integer, integer)" in sql
    assert "grant select, insert on lead_followups" in sql
    assert "grant insert on security_events" in sql
    assert "bypassrls" not in sql


def test_inactive_visit_report_scheduler_is_deduplicated_and_least_privilege() -> None:
    sql = VISIT_NOTIFICATION_MIGRATION.read_text(encoding="utf-8").lower()
    assert "security definer" in sql
    assert "set search_path = pg_catalog, public, app" in sql
    assert "for update of visit skip locked" in sql
    assert "visit-report:" in sql
    assert "on conflict (tenant_id, company_id, deduplication_key) do nothing" in sql
    assert "revoke all on function app.enqueue_inactive_visit_reports" in sql
    assert "grant execute on function" in sql
    assert "cf_ai_card_worker" in sql
    assert "bypassrls" not in sql


def test_visit_report_rollout_does_not_notify_for_historical_visits() -> None:
    sql = VISIT_ROLLOUT_GUARD_MIGRATION.read_text(encoding="utf-8").lower()
    assert "visit-started:" in sql
    assert "visit-report-legacy-suppressed-v1" in sql
    assert "on conflict (event_id, handler_name) do nothing" in sql
    assert "status = 'published'" in sql
