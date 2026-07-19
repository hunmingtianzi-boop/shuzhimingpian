"""Restore least-privilege grants after a data-only or no-ACL database restore.

Revision ID: 20260719_0024
Revises: 20260717_0023
"""

from alembic import op

revision = "20260719_0024"
down_revision = "20260717_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT USAGE ON SCHEMA public, app TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON
              tenants, companies, users, memberships, auth_sessions, cards,
              visitors, visitor_profiles, consent_records, visits, visit_events,
              conversations, messages, prompt_versions, model_configs, ai_runs,
              knowledge_documents, knowledge_versions, knowledge_chunks,
              message_citations, knowledge_index_jobs, knowledge_gaps,
              visit_summaries, idempotency_keys, audit_logs, outbox_events
              TO cf_ai_card_app;
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.current_tenant_id() TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.current_company_id() TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.current_card_slug() TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.scope_matches(uuid, uuid) TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.touch_updated_at() TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.guard_immutable_content() TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.enforce_knowledge_activation() TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.reject_audit_mutation() TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.erase_visitor_lead_followups(uuid, uuid, uuid) TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.platform_actor_allowed() TO cf_ai_card_app;

            GRANT SELECT, INSERT, UPDATE, DELETE ON staff_credentials TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON
              products, case_studies, forbidden_topics, card_contact_fields,
              privacy_requests, leads, notifications
              TO cf_ai_card_app;
            GRANT SELECT, INSERT ON lead_followups TO cf_ai_card_app;
            GRANT INSERT ON security_events TO cf_ai_card_app;
            GRANT SELECT ON outbox_deliveries, worker_job_results TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE ON data_export_requests TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON visitor_profile_signals
              TO cf_ai_card_app;
            GRANT SELECT, INSERT ON visitor_profile_signal_sources TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE ON scheduled_publish_jobs TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE ON
              knowledge_import_batches, knowledge_import_items TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE, DELETE ON
              enterprise_content_distributions, card_content_overrides,
              card_content_override_revisions
              TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE ON platform_llm_profiles TO cf_ai_card_app;
            GRANT SELECT, INSERT, UPDATE ON platform_onboarding_sessions
              TO cf_ai_card_app;

            GRANT EXECUTE ON FUNCTION app.platform_operations_overview()
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_company_aggregates(integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_tasks(integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_audit(integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_transition_enterprise(uuid, integer, text)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_enterprises(text, text, integer, integer)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_enterprise_detail(uuid, text)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.platform_onboarding_imports_settled(uuid)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.platform_onboarding_drafts(uuid)
              TO cf_ai_card_app;
          END IF;

          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT USAGE ON SCHEMA public, app TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION app.claim_outbox_events(text, integer, integer)
              TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION app.purge_expired_visitor_profiles()
              TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION
              app.claim_scheduled_publish_jobs(text, integer, integer)
              TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION
              app.claim_knowledge_import_items(text, integer, integer)
              TO cf_ai_card_worker;
            GRANT EXECUTE ON FUNCTION app.platform_actor_allowed()
              TO cf_ai_card_worker;

            GRANT SELECT, UPDATE ON outbox_events TO cf_ai_card_worker;
            GRANT SELECT, INSERT ON outbox_deliveries TO cf_ai_card_worker;
            GRANT SELECT, INSERT, UPDATE ON worker_job_results TO cf_ai_card_worker;
            GRANT SELECT, INSERT ON notifications TO cf_ai_card_worker;
            GRANT SELECT ON
              tenants, companies, memberships, cards, privacy_requests,
              visit_summaries, conversations, prompt_versions, model_configs,
              visitors, visitor_profiles, visits, leads, messages
              TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON data_export_requests TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON scheduled_publish_jobs TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON products, case_studies TO cf_ai_card_worker;
            GRANT SELECT, INSERT, UPDATE ON
              knowledge_documents, knowledge_versions, knowledge_chunks,
              knowledge_index_jobs
              TO cf_ai_card_worker;
            GRANT SELECT, INSERT ON audit_logs TO cf_ai_card_worker;
            GRANT SELECT, UPDATE ON
              knowledge_import_batches, knowledge_import_items
              TO cf_ai_card_worker;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    # This is a repair-only migration. Earlier revisions own the grants, so a
    # downgrade must not revoke privileges that their schema still requires.
    pass
