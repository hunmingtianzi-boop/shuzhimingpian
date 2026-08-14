"""Add onboarding names, credential regeneration and retention cleanup.

Revision ID: 20260814_0038
Revises: 20260813_0037
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260814_0038"
down_revision: str | None = "20260813_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column("display_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column("retention_cleanup_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column(
            "purge_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.execute(
        """
        WITH ranked AS (
          SELECT
            id,
            row_number() OVER (
              PARTITION BY created_by ORDER BY created_at, id
            ) AS sequence_number
          FROM platform_onboarding_sessions
        )
        UPDATE platform_onboarding_sessions AS onboarding
        SET display_name = pg_catalog.left(
          COALESCE(
            NULLIF(pg_catalog.btrim(onboarding.tenant_name), ''),
            onboarding.tenant_slug
          ) || '·资料导入·' ||
          pg_catalog.to_char(onboarding.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') ||
          '·第 ' || ranked.sequence_number::text || ' 次',
          200
        )
        FROM ranked
        WHERE ranked.id = onboarding.id
        """
    )
    op.execute(
        """
        UPDATE platform_onboarding_sessions
        SET retention_cleanup_after =
          COALESCE(cancelled_at, updated_at) + interval '30 days'
        WHERE status IN ('cancelled','expired','failed')
          AND confirmed_at IS NULL
          AND retention_cleanup_after IS NULL
        """
    )
    op.alter_column(
        "platform_onboarding_sessions",
        "display_name",
        existing_type=sa.String(length=200),
        nullable=False,
    )
    op.create_check_constraint(
        "display_name_non_empty",
        "platform_onboarding_sessions",
        "char_length(btrim(display_name)) > 0",
    )
    op.create_index(
        "ix_platform_onboarding_retention_cleanup",
        "platform_onboarding_sessions",
        ["retention_cleanup_after"],
        postgresql_where=sa.text(
            "status IN ('cancelled','expired','failed') "
            "AND confirmed_at IS NULL AND purged_at IS NULL"
        ),
    )

    confirmed_credential = (
        "app.platform_actor_allowed() AND EXISTS ("
        "SELECT 1 FROM platform_onboarding_sessions AS onboarding "
        "WHERE onboarding.credential_id = staff_credentials.id "
        "AND onboarding.status = 'confirmed' "
        "AND onboarding.confirmed_at IS NOT NULL "
        "AND onboarding.created_by = "
        "NULLIF(current_setting('app.user_id', true), '')::uuid)"
    )
    op.execute(
        "CREATE POLICY staff_credentials_platform_onboarding_confirmed_select "
        "ON staff_credentials FOR SELECT "
        f"USING ({confirmed_credential})"
    )
    op.execute(
        "CREATE POLICY staff_credentials_platform_onboarding_confirmed_update "
        "ON staff_credentials FOR UPDATE "
        f"USING ({confirmed_credential}) "
        f"WITH CHECK ({confirmed_credential} AND is_enabled AND must_change_password)"
    )

    # One owner-scoped database round trip projects the latest review attached
    # to each listed onboarding session. This keeps platform list/detail
    # recoverable without weakening company-scoped RLS or introducing N+1
    # queries across provisional companies.
    op.execute(
        """
        CREATE FUNCTION app.platform_onboarding_content_reviews(p_session_ids uuid[])
        RETURNS TABLE(session_id uuid, review jsonb)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
          SELECT onboarding.id,
                 pg_catalog.jsonb_build_object(
                   'id', review_run.id,
                   'batch_id', review_run.batch_id,
                   'status', review_run.status,
                   'provider', review_run.provider,
                   'model', review_run.model,
                   'attempts', review_run.attempts,
                   'failure_code', review_run.failure_code,
                   'counts', review_run.counts,
                   'candidates', COALESCE(
                     candidate_rows.items,
                     '[]'::jsonb
                   ),
                   'completed_at', review_run.completed_at,
                   'created_at', review_run.created_at,
                   'updated_at', review_run.updated_at
                 ) AS review
          FROM public.platform_onboarding_sessions AS onboarding
          JOIN LATERAL (
            SELECT candidate_run.*
            FROM pg_catalog.unnest(onboarding.import_batch_ids)
              WITH ORDINALITY AS bound_batch(batch_id, bound_order)
            JOIN public.content_import_runs AS candidate_run
              ON candidate_run.batch_id = bound_batch.batch_id
             AND candidate_run.tenant_id = onboarding.tenant_id
             AND candidate_run.company_id = onboarding.company_id
            ORDER BY bound_batch.bound_order DESC,
                     candidate_run.created_at DESC,
                     candidate_run.id DESC
            LIMIT 1
          ) AS review_run ON true
          LEFT JOIN LATERAL (
            SELECT pg_catalog.jsonb_agg(
                     pg_catalog.jsonb_build_object(
                       'id', candidate.id,
                       'run_id', candidate.run_id,
                       'category', candidate.category,
                       'payload', candidate.payload,
                       'source_id', candidate.source_id,
                       'source_text', candidate.source_text,
                       'confidence', candidate.confidence,
                       'status', candidate.status,
                       'target_resource_type', candidate.target_resource_type,
                       'target_resource_id', candidate.target_resource_id,
                       'version', candidate.version,
                       'created_at', candidate.created_at,
                       'updated_at', candidate.updated_at
                     )
                     ORDER BY candidate.created_at, candidate.id
                   ) AS items
            FROM public.content_import_candidates AS candidate
            WHERE candidate.run_id = review_run.id
              AND candidate.tenant_id = onboarding.tenant_id
              AND candidate.company_id = onboarding.company_id
          ) AS candidate_rows ON true
          WHERE app.platform_actor_allowed()
            AND onboarding.created_by = NULLIF(
                  pg_catalog.current_setting('app.user_id', true), ''
                )::uuid
            AND onboarding.id = ANY(p_session_ids)
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.platform_onboarding_content_reviews(uuid[]) FROM PUBLIC")
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'cf_ai_card_app'
          ) THEN
            GRANT EXECUTE ON FUNCTION
              app.platform_onboarding_content_reviews(uuid[])
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )

    # Audit logs deliberately remain FK-bound to the tenant/company. The
    # cleanup therefore removes temporary import/review rows, scrubs content,
    # disables credentials and soft-deletes core provisional resources rather
    # than risking a broad cascading tenant delete.
    op.execute(
        """
        CREATE FUNCTION app.purge_expired_platform_onboarding_sessions()
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = ''
        AS $$
        DECLARE
          target record;
          affected integer;
          scrubbed integer;
          expired_count integer := 0;
          purged_count integer := 0;
          imports_deleted integer;
          candidates_deleted integer;
          resources_scrubbed integer;
        BEGIN
          UPDATE public.platform_onboarding_sessions
          SET status = 'expired',
              retention_cleanup_after = pg_catalog.clock_timestamp() + interval '30 days',
              version = version + 1
          WHERE status IN
              ('draft','processing','review','manual_required','ready_to_confirm')
            AND expires_at <= pg_catalog.clock_timestamp()
            AND confirmed_at IS NULL
            AND purged_at IS NULL;
          GET DIAGNOSTICS expired_count = ROW_COUNT;

          FOR target IN
            SELECT onboarding.*
            FROM public.platform_onboarding_sessions AS onboarding
            WHERE onboarding.status IN ('cancelled','expired','failed')
              AND onboarding.confirmed_at IS NULL
              AND onboarding.confirmed_enterprise IS NULL
              AND onboarding.retention_cleanup_after <= pg_catalog.clock_timestamp()
              AND onboarding.purged_at IS NULL
            ORDER BY onboarding.retention_cleanup_after, onboarding.id
            FOR UPDATE SKIP LOCKED
            LIMIT 100
          LOOP
            imports_deleted := 0;
            candidates_deleted := 0;
            resources_scrubbed := 0;
            scrubbed := 0;

            UPDATE public.products
            SET name = '[purged provisional product]',
                summary = '', detail = '', audience = NULL,
                price_boundary = NULL, image_url = NULL,
                status = 'archived', published_at = NULL,
                settings = '{}'::jsonb,
                deleted_at = pg_catalog.clock_timestamp(), deleted_by = NULL
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS affected = ROW_COUNT;
            scrubbed := scrubbed + affected;

            UPDATE public.case_studies
            SET title = '[purged provisional case]',
                background = '', solution = '', result = '',
                client_display_name = NULL, image_url = NULL,
                status = 'archived', published_at = NULL,
                deleted_at = pg_catalog.clock_timestamp(), deleted_by = NULL
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS affected = ROW_COUNT;
            scrubbed := scrubbed + affected;

            UPDATE public.knowledge_chunks
            SET title = '[purged]', text = '[purged]', token_count = 1,
                embedding = NULL, embedding_model = NULL, is_active = false,
                content_hash = pg_catalog.repeat('0', 64), metadata = '{}'::jsonb
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS affected = ROW_COUNT;
            scrubbed := scrubbed + affected;

            UPDATE public.knowledge_versions
            SET raw_text = '[purged]', content_hash = pg_catalog.repeat('0', 64),
                review_status = 'archived', reviewed_by = NULL,
                reviewed_at = NULL, published_at = NULL
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS affected = ROW_COUNT;
            scrubbed := scrubbed + affected;

            UPDATE public.knowledge_documents
            SET title = '[purged provisional document]', status = 'archived',
                current_version_id = NULL
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS affected = ROW_COUNT;
            scrubbed := scrubbed + affected;

            DELETE FROM public.content_import_candidates
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS candidates_deleted = ROW_COUNT;
            DELETE FROM public.content_import_runs
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            DELETE FROM public.knowledge_import_items
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS affected = ROW_COUNT;
            imports_deleted := imports_deleted + affected;
            DELETE FROM public.knowledge_import_batches
            WHERE tenant_id = target.tenant_id AND company_id = target.company_id;
            GET DIAGNOSTICS affected = ROW_COUNT;
            imports_deleted := imports_deleted + affected;

            UPDATE public.staff_credentials
            SET is_enabled = false, must_change_password = false,
                temporary_password_expires_at = NULL,
                failed_attempts = 0, locked_until = NULL, last_failed_at = NULL,
                account_normalized = 'purged-' || id::text || '@invalid.local'
            WHERE id = target.credential_id;
            UPDATE public.memberships
            SET status = 'disabled', permissions = '{}'::varchar[]
            WHERE id = target.admin_membership_id;
            UPDATE public.users
            SET display_name = '[purged provisional user]',
                email_ciphertext = NULL, email_hmac = NULL,
                mobile_ciphertext = NULL, mobile_hmac = NULL,
                status = 'disabled', deleted_at = pg_catalog.clock_timestamp(),
                deleted_by = NULL
            WHERE id = target.admin_user_id;
            UPDATE public.cards
            SET display_name = '[purged provisional card]', status = 'archived',
                settings = '{}'::jsonb,
                deleted_at = pg_catalog.clock_timestamp(), deleted_by = NULL
            WHERE id = target.initial_card_id;
            UPDATE public.companies
            SET name = '[purged provisional company]',
                normalized_name = 'purged-' || id::text,
                industry = NULL, status = 'disabled', settings = '{}'::jsonb,
                deleted_at = pg_catalog.clock_timestamp(), deleted_by = NULL
            WHERE id = target.company_id AND tenant_id = target.tenant_id;
            UPDATE public.tenants
            SET slug = 'purged-' || id::text,
                name = '[purged provisional tenant]', status = 'disabled',
                settings = '{}'::jsonb,
                deleted_at = pg_catalog.clock_timestamp(), deleted_by = NULL
            WHERE id = target.tenant_id;
            resources_scrubbed := scrubbed + 6;

            UPDATE public.platform_onboarding_sessions
            SET display_name = '[purged] ' || id::text,
                tenant_slug = 'purged-' || tenant_id::text,
                tenant_name = NULL,
                admin_account = '[purged]',
                import_batch_ids = '{}'::uuid[],
                suggestions = '[]'::jsonb,
                business_profile = '[]'::jsonb,
                purged_at = pg_catalog.clock_timestamp(),
                purge_summary = pg_catalog.jsonb_build_object(
                  'imports_deleted', imports_deleted,
                  'candidates_deleted', candidates_deleted,
                  'resources_scrubbed', resources_scrubbed,
                  'core_resource_disposition', 'scrubbed_and_soft_deleted',
                  'audit_logs_retained', true
                ),
                version = version + 1
            WHERE id = target.id
              AND status IN ('cancelled','expired','failed')
              AND confirmed_at IS NULL;
            purged_count := purged_count + 1;
          END LOOP;
          RETURN expired_count + purged_count;
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.purge_expired_platform_onboarding_sessions() FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'cf_ai_card_worker'
          ) THEN
            GRANT EXECUTE ON FUNCTION
              app.purge_expired_platform_onboarding_sessions()
              TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.purge_expired_platform_onboarding_sessions()")
    op.execute("DROP FUNCTION IF EXISTS app.platform_onboarding_content_reviews(uuid[])")
    op.execute(
        "DROP POLICY IF EXISTS staff_credentials_platform_onboarding_confirmed_update "
        "ON staff_credentials"
    )
    op.execute(
        "DROP POLICY IF EXISTS staff_credentials_platform_onboarding_confirmed_select "
        "ON staff_credentials"
    )
    op.drop_index(
        "ix_platform_onboarding_retention_cleanup",
        table_name="platform_onboarding_sessions",
    )
    op.drop_constraint(
        op.f("ck_platform_onboarding_sessions_display_name_non_empty"),
        "platform_onboarding_sessions",
        type_="check",
    )
    op.drop_column("platform_onboarding_sessions", "purge_summary")
    op.drop_column("platform_onboarding_sessions", "purged_at")
    op.drop_column("platform_onboarding_sessions", "retention_cleanup_after")
    op.drop_column("platform_onboarding_sessions", "display_name")
