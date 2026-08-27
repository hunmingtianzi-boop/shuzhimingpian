"""Project onboarding review candidates from every attached source batch.

Revision ID: 20260826_0051
Revises: 20260826_0050
"""

from alembic import op

revision = "20260826_0051"
down_revision = "20260826_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.platform_onboarding_content_reviews(uuid[])")
    op.execute(
        """
        CREATE FUNCTION app.platform_onboarding_content_reviews(p_session_ids uuid[])
        RETURNS TABLE(session_id uuid, review jsonb)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = ''
        AS $$
          WITH latest_runs AS (
            SELECT onboarding.id AS session_id,
                   candidate_run.*,
                   bound_batch.bound_order,
                   pg_catalog.row_number() OVER (
                     PARTITION BY onboarding.id, bound_batch.batch_id
                     ORDER BY candidate_run.created_at DESC, candidate_run.id DESC
                   ) AS run_order
            FROM public.platform_onboarding_sessions AS onboarding
            CROSS JOIN LATERAL pg_catalog.unnest(onboarding.import_batch_ids)
              WITH ORDINALITY AS bound_batch(batch_id, bound_order)
            JOIN public.content_import_runs AS candidate_run
              ON candidate_run.batch_id = bound_batch.batch_id
             AND candidate_run.tenant_id = onboarding.tenant_id
             AND candidate_run.company_id = onboarding.company_id
            WHERE app.platform_actor_allowed()
              AND onboarding.created_by = NULLIF(
                    pg_catalog.current_setting('app.user_id', true), ''
                  )::uuid
              AND onboarding.id = ANY(p_session_ids)
          ),
          selected_runs AS (
            SELECT * FROM latest_runs WHERE run_order = 1
          ),
          run_summary AS (
            SELECT session_id,
                   (pg_catalog.array_agg(id ORDER BY bound_order DESC))[1] AS id,
                   (pg_catalog.array_agg(batch_id ORDER BY bound_order DESC))[1] AS batch_id,
                   pg_catalog.array_agg(id) AS run_ids,
                   CASE
                     WHEN pg_catalog.bool_or(status = 'processing') THEN 'processing'
                     WHEN pg_catalog.bool_or(status = 'review') THEN 'review'
                     ELSE 'manual_required'
                   END AS status,
                   (pg_catalog.array_agg(provider ORDER BY bound_order DESC))[1] AS provider,
                   (pg_catalog.array_agg(model ORDER BY bound_order DESC))[1] AS model,
                   pg_catalog.max(attempts) AS attempts,
                   (pg_catalog.array_agg(failure_code ORDER BY bound_order DESC)
                     FILTER (WHERE failure_code IS NOT NULL))[1] AS failure_code,
                   CASE
                     WHEN pg_catalog.bool_or(status = 'processing') THEN 'enriching'
                     WHEN pg_catalog.bool_and(stage = 'failed') THEN 'failed'
                     ELSE 'completed'
                   END AS stage,
                   pg_catalog.sum(progress_current)::integer AS progress_current,
                   GREATEST(pg_catalog.sum(progress_total)::integer, 1) AS progress_total,
                   pg_catalog.max(job_attempts) AS job_attempts,
                   pg_catalog.max(started_at) AS started_at,
                   CASE WHEN pg_catalog.bool_or(status = 'processing')
                     THEN NULL ELSE pg_catalog.max(completed_at) END AS completed_at,
                   pg_catalog.min(created_at) AS created_at,
                   pg_catalog.max(updated_at) AS updated_at,
                   pg_catalog.count(*)::integer AS source_count,
                   pg_catalog.count(*) FILTER (WHERE status <> 'processing')::integer AS processed_count
            FROM selected_runs
            GROUP BY session_id
          )
          SELECT summary.session_id,
                 pg_catalog.jsonb_build_object(
                   'id', summary.id,
                   'batch_id', summary.batch_id,
                   'status', summary.status,
                   'provider', summary.provider,
                   'model', summary.model,
                   'attempts', summary.attempts,
                   'failure_code', summary.failure_code,
                   'counts', COALESCE(count_rows.counts, '{}'::jsonb),
                   'stage', summary.stage,
                   'stage_message', CASE
                     WHEN summary.status = 'processing' THEN pg_catalog.format(
                       '正在分析 %s/%s 份资料', summary.processed_count, summary.source_count
                     )
                     ELSE pg_catalog.format(
                       '已完成 %s 份资料分析，共生成 %s 条候选',
                       summary.source_count, COALESCE(candidate_rows.candidate_count, 0)
                     )
                   END,
                   'progress_current', summary.progress_current,
                   'progress_total', summary.progress_total,
                   'job_attempts', summary.job_attempts,
                   'candidates', COALESCE(candidate_rows.items, '[]'::jsonb),
                   'started_at', summary.started_at,
                   'completed_at', summary.completed_at,
                   'created_at', summary.created_at,
                   'updated_at', summary.updated_at
                 ) AS review
          FROM run_summary AS summary
          LEFT JOIN LATERAL (
            SELECT pg_catalog.jsonb_object_agg(category, total) AS counts
            FROM (
              SELECT count_entry.key AS category,
                     pg_catalog.sum(count_entry.value::integer) AS total
              FROM selected_runs AS selected
              CROSS JOIN LATERAL pg_catalog.jsonb_each_text(selected.counts)
                AS count_entry(key, value)
              WHERE selected.session_id = summary.session_id
              GROUP BY count_entry.key
            ) AS totals
          ) AS count_rows ON true
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
                       'enrichment_status', candidate.enrichment_status,
                       'field_warnings', candidate.field_warnings,
                       'target_resource_type', candidate.target_resource_type,
                       'target_resource_id', candidate.target_resource_id,
                       'version', candidate.version,
                       'created_at', candidate.created_at,
                       'updated_at', candidate.updated_at
                     ) ORDER BY candidate.created_at, candidate.id
                   ) AS items,
                   pg_catalog.count(*)::integer AS candidate_count
            FROM public.content_import_candidates AS candidate
            WHERE candidate.run_id = ANY(summary.run_ids)
          ) AS candidate_rows ON true
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.platform_onboarding_content_reviews(uuid[]) FROM PUBLIC")
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT EXECUTE ON FUNCTION app.platform_onboarding_content_reviews(uuid[])
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    # The previous migration owns the single-source definition. Downgrades in
    # this development line remove the v2 projection before 0050 is reverted.
    op.execute("DROP FUNCTION IF EXISTS app.platform_onboarding_content_reviews(uuid[])")
