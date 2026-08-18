"""Add progressive background content-import task state.

Revision ID: 20260819_0044
Revises: 20260819_0043
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260819_0044"
down_revision: str | None = "20260819_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "content_import_runs",
        sa.Column("stage", sa.String(24), nullable=False, server_default="queued"),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("stage_message", sa.String(240), nullable=True),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("job_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("max_job_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "content_import_runs",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("lock_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("locked_by", sa.String(128), nullable=True),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_import_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "content_import_candidates",
        sa.Column(
            "enrichment_status",
            sa.String(24),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "content_import_candidates",
        sa.Column(
            "field_warnings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "content_import_run_stage_allowed",
        "content_import_runs",
        "stage IN ('queued','discovering','enriching','validating',"
        "'finalizing','completed','failed')",
    )
    op.create_check_constraint(
        "content_import_run_progress_valid",
        "content_import_runs",
        "progress_current >= 0 AND progress_total >= 1 AND progress_current <= progress_total",
    )
    op.create_check_constraint(
        "content_import_run_job_attempts_valid",
        "content_import_runs",
        "job_attempts >= 0 AND max_job_attempts > 0 AND job_attempts <= max_job_attempts",
    )
    op.create_check_constraint(
        "content_import_candidate_enrichment_status_allowed",
        "content_import_candidates",
        "enrichment_status IN ('pending','processing','completed','needs_review')",
    )
    op.create_index(
        "ix_content_import_runs_due",
        "content_import_runs",
        ["status", "stage", "next_attempt_at", "created_at"],
    )
    op.execute(
        """
        UPDATE content_import_runs
        SET stage = CASE
            WHEN status = 'processing' THEN 'failed'
            ELSE 'completed'
        END,
        stage_message = CASE
            WHEN status = 'processing' THEN '历史同步任务已中断，可安全重试'
            ELSE '历史任务已完成'
        END,
        progress_current = 1,
        progress_total = 1,
        completed_at = CASE
            WHEN status = 'processing' THEN COALESCE(completed_at, updated_at)
            ELSE completed_at
        END,
        status = CASE
            WHEN status = 'processing' THEN 'manual_required'
            ELSE status
        END
        """
    )
    op.execute(
        """
        UPDATE content_import_candidates
        SET enrichment_status = CASE
            WHEN status = 'pending_review' THEN 'completed'
            ELSE 'completed'
        END
        """
    )
    op.execute(
        """
        CREATE FUNCTION app.claim_content_import_runs(
            worker_name text,
            batch_limit integer,
            lease_seconds integer
        ) RETURNS TABLE(
            run_id uuid,
            tenant_id uuid,
            company_id uuid,
            lock_token uuid,
            requested_by uuid,
            job_attempts integer,
            max_job_attempts integer
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $function$
        BEGIN
          IF worker_name IS NULL OR btrim(worker_name) = '' THEN
            RAISE EXCEPTION 'worker_name is required';
          END IF;
          IF batch_limit < 1 OR batch_limit > 100 OR lease_seconds < 30 OR lease_seconds > 3600 THEN
            RAISE EXCEPTION 'invalid content import claim limits';
          END IF;
          RETURN QUERY
          WITH due AS (
            SELECT run.id
            FROM public.content_import_runs AS run
            WHERE run.status = 'processing'
              AND (
                run.stage = 'queued'
                OR (
                  run.stage IN ('discovering','enriching','validating','finalizing')
                  AND run.lease_expires_at <= clock_timestamp()
                )
              )
              AND run.next_attempt_at <= clock_timestamp()
              AND run.job_attempts < run.max_job_attempts
            ORDER BY run.created_at, run.id
            FOR UPDATE SKIP LOCKED
            LIMIT batch_limit
          ), claimed AS (
            UPDATE public.content_import_runs AS run
            SET stage = 'discovering',
                stage_message = '正在识别候选目录',
                progress_current = 0,
                progress_total = 1,
                job_attempts = run.job_attempts + 1,
                lock_token = gen_random_uuid(),
                locked_by = worker_name,
                lease_expires_at = clock_timestamp() + make_interval(secs => lease_seconds),
                started_at = COALESCE(run.started_at, clock_timestamp()),
                failure_code = NULL
            FROM due
            WHERE run.id = due.id
            RETURNING run.*
          )
          SELECT claimed.id, claimed.tenant_id, claimed.company_id,
                 claimed.lock_token, claimed.requested_by,
                 claimed.job_attempts, claimed.max_job_attempts
          FROM claimed;
        END
        $function$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.claim_content_import_runs(text, integer, integer) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "app.claim_content_import_runs(text, integer, integer) TO cf_ai_card_worker"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON "
        "content_import_runs, content_import_candidates TO cf_ai_card_worker"
    )
    op.execute("GRANT SELECT ON platform_llm_profiles TO cf_ai_card_worker")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON platform_llm_profiles FROM cf_ai_card_worker")
    op.execute(
        "REVOKE ALL ON FUNCTION app.claim_content_import_runs(text, integer, integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.claim_content_import_runs(text, integer, integer)")
    op.drop_index("ix_content_import_runs_due", table_name="content_import_runs")
    op.drop_constraint(
        "content_import_candidate_enrichment_status_allowed",
        "content_import_candidates",
        type_="check",
    )
    op.drop_constraint(
        "content_import_run_job_attempts_valid", "content_import_runs", type_="check"
    )
    op.drop_constraint(
        "content_import_run_progress_valid", "content_import_runs", type_="check"
    )
    op.drop_constraint(
        "content_import_run_stage_allowed", "content_import_runs", type_="check"
    )
    op.drop_column("content_import_candidates", "field_warnings")
    op.drop_column("content_import_candidates", "enrichment_status")
    op.drop_column("content_import_runs", "started_at")
    op.drop_column("content_import_runs", "lease_expires_at")
    op.drop_column("content_import_runs", "locked_by")
    op.drop_column("content_import_runs", "lock_token")
    op.drop_column("content_import_runs", "next_attempt_at")
    op.drop_column("content_import_runs", "max_job_attempts")
    op.drop_column("content_import_runs", "job_attempts")
    op.drop_column("content_import_runs", "progress_total")
    op.drop_column("content_import_runs", "progress_current")
    op.drop_column("content_import_runs", "stage_message")
    op.drop_column("content_import_runs", "stage")
