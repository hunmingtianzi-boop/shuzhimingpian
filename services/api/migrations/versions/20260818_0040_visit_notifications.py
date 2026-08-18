"""Add inactive visit report notification scheduling.

Revision ID: 20260818_0040
Revises: 20260817_0039
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0040"
down_revision: str | None = "20260817_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app.enqueue_inactive_visit_reports(
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
            SELECT
              visit.id,
              visit.tenant_id,
              visit.company_id,
              visit.card_id
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
              AND EXISTS (
                SELECT 1
                FROM public.outbox_events AS started
                WHERE started.tenant_id = visit.tenant_id
                  AND started.company_id = visit.company_id
                  AND started.deduplication_key =
                    'visit-started:' || visit.id::text
              )
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
                  AND queued.deduplication_key = 'visit-report:' || visit.id::text
              )
            ORDER BY visit.started_at, visit.id
            FOR UPDATE OF visit SKIP LOCKED
            LIMIT p_batch_size
          )
          INSERT INTO public.outbox_events (
            id,
            tenant_id,
            company_id,
            aggregate_type,
            aggregate_id,
            aggregate_version,
            event_type,
            payload,
            headers,
            deduplication_key,
            status
          )
          SELECT
            gen_random_uuid(),
            candidate.tenant_id,
            candidate.company_id,
            'visit',
            candidate.id,
            1,
            'visit.report.ready.v1',
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
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.enqueue_inactive_visit_reports(integer, integer) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT EXECUTE ON FUNCTION
              app.enqueue_inactive_visit_reports(integer, integer)
              TO cf_ai_card_worker;
            GRANT SELECT ON visit_events TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION app.enqueue_inactive_visit_reports(integer, integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.enqueue_inactive_visit_reports(integer, integer)")
