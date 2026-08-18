"""Prevent historical visit backfill and suppress rollout-only events.

Revision ID: 20260818_0042
Revises: 20260818_0041
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0042"
down_revision: str | None = "20260818_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _scheduler_sql(*, require_started_event: bool) -> str:
    rollout_guard = (
        """
              AND EXISTS (
                SELECT 1
                FROM public.outbox_events AS started
                WHERE started.tenant_id = visit.tenant_id
                  AND started.company_id = visit.company_id
                  AND started.deduplication_key =
                    'visit-started:' || visit.id::text
              )
        """
        if require_started_event
        else ""
    )
    # The only interpolated fragment is the static migration-owned guard above.
    return f"""
        CREATE OR REPLACE FUNCTION app.enqueue_inactive_visit_reports(
          p_batch_size integer,
          p_idle_seconds integer
        ) RETURNS integer
        LANGUAGE plpgsql
        VOLATILE
        PARALLEL UNSAFE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          inserted_count integer;
        BEGIN
          IF p_batch_size NOT BETWEEN 1 AND 500
             OR p_idle_seconds NOT BETWEEN 60 AND 86400 THEN
            RAISE EXCEPTION 'invalid inactive visit report parameters'
              USING ERRCODE = '22023';
          END IF;

          WITH candidates AS (
            SELECT visit.id, visit.tenant_id, visit.company_id, visit.card_id
            FROM public.visits AS visit
            JOIN public.companies AS company
              ON company.id = visit.company_id
             AND company.tenant_id = visit.tenant_id
            WHERE EXISTS (
              SELECT 1
              FROM public.visit_events AS page_view
              WHERE page_view.tenant_id = visit.tenant_id
                AND page_view.company_id = visit.company_id
                AND page_view.visit_id = visit.id
                AND page_view.event_type = 'page_view'
            )
              {rollout_guard}
              AND COALESCE(
                (
                  SELECT max(activity.occurred_at)
                  FROM public.visit_events AS activity
                  WHERE activity.tenant_id = visit.tenant_id
                    AND activity.company_id = visit.company_id
                    AND activity.visit_id = visit.id
                ),
                visit.started_at
              ) <= clock_timestamp() - make_interval(secs => p_idle_seconds)
              AND COALESCE(
                company.settings -> 'visit_notifications' ->> 'enabled',
                'true'
              ) = 'true'
              AND COALESCE(
                company.settings -> 'visit_notifications' ->> 'report_enabled',
                'true'
              ) = 'true'
              AND NOT EXISTS (
                SELECT 1
                FROM public.outbox_events AS queued
                WHERE queued.tenant_id = visit.tenant_id
                  AND queued.company_id = visit.company_id
                  AND queued.deduplication_key =
                    'visit-report:' || visit.id::text
              )
            ORDER BY visit.started_at, visit.id
            FOR UPDATE OF visit SKIP LOCKED
            LIMIT p_batch_size
          )
          INSERT INTO public.outbox_events (
            id, tenant_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload, headers,
            deduplication_key, status
          )
          SELECT
            gen_random_uuid(), candidate.tenant_id, candidate.company_id,
            'visit', candidate.id, 1, 'visit.report.ready.v1',
            jsonb_build_object(
              'visit_id', candidate.id::text,
              'card_id', candidate.card_id::text
            ),
            jsonb_build_object('contains_pii', false),
            'visit-report:' || candidate.id::text,
            'pending'
          FROM candidates AS candidate
          ON CONFLICT (tenant_id, company_id, deduplication_key) DO NOTHING;

          GET DIAGNOSTICS inserted_count = ROW_COUNT;
          RETURN inserted_count;
        END
        $$
    """  # noqa: S608


def upgrade() -> None:
    op.execute(_scheduler_sql(require_started_event=True))
    op.execute(
        """
        INSERT INTO public.outbox_deliveries (
          id, tenant_id, company_id, event_id, handler_name,
          result_hash, completed_at
        )
        SELECT
          gen_random_uuid(), report.tenant_id, report.company_id, report.id,
          'visit-report-legacy-suppressed-v1', repeat('0', 64),
          clock_timestamp()
        FROM public.outbox_events AS report
        WHERE report.event_type = 'visit.report.ready.v1'
          AND report.status <> 'published'
          AND NOT EXISTS (
            SELECT 1
            FROM public.outbox_events AS started
            WHERE started.tenant_id = report.tenant_id
              AND started.company_id = report.company_id
              AND started.deduplication_key =
                'visit-started:' || report.aggregate_id::text
          )
        ON CONFLICT (event_id, handler_name) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE public.outbox_events AS report
        SET status = 'published',
            published_at = COALESCE(report.published_at, clock_timestamp()),
            locked_at = NULL,
            locked_by = NULL,
            lock_token = NULL,
            lease_expires_at = NULL,
            last_error = NULL,
            updated_at = clock_timestamp()
        WHERE report.event_type = 'visit.report.ready.v1'
          AND report.status <> 'published'
          AND NOT EXISTS (
            SELECT 1
            FROM public.outbox_events AS started
            WHERE started.tenant_id = report.tenant_id
              AND started.company_id = report.company_id
              AND started.deduplication_key =
                'visit-started:' || report.aggregate_id::text
          )
        """
    )


def downgrade() -> None:
    op.execute(_scheduler_sql(require_started_event=False))
