"""Add daily digest outbox scheduling for ordinary visits.

Revision ID: 20260823_0048
Revises: 20260823_0047
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260823_0048"
down_revision: str | None = "20260823_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION app.enqueue_visit_daily_digests(
          p_batch_size integer
        ) RETURNS integer
        LANGUAGE plpgsql
        VOLATILE
        PARALLEL UNSAFE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          inserted_count integer;
          digest_day date := (clock_timestamp() AT TIME ZONE 'UTC')::date - 1;
        BEGIN
          IF p_batch_size NOT BETWEEN 1 AND 500 THEN
            RAISE EXCEPTION 'invalid visit daily digest batch size'
              USING ERRCODE = '22023';
          END IF;

          WITH candidate_companies AS (
            SELECT DISTINCT
              visit.tenant_id,
              visit.company_id
            FROM public.visits AS visit
            JOIN public.companies AS company
              ON company.id = visit.company_id
             AND company.tenant_id = visit.tenant_id
            WHERE visit.started_at >= digest_day::timestamptz
              AND visit.started_at < (digest_day::timestamptz + interval '1 day')
              AND coalesce(
                company.settings -> 'visit_notifications' ->> 'enabled',
                'true'
              ) = 'true'
              AND coalesce(
                company.settings -> 'visit_notifications' ->> 'ordinary_visit_digest_enabled',
                'true'
              ) = 'true'
              AND EXISTS (
                SELECT 1
                FROM public.cards AS card
                WHERE card.id = visit.card_id
                  AND card.tenant_id = visit.tenant_id
                  AND card.company_id = visit.company_id
              )
              AND NOT EXISTS (
                SELECT 1
                FROM public.conversations AS conversation
                JOIN public.leads AS lead
                  ON lead.tenant_id = conversation.tenant_id
                 AND lead.company_id = conversation.company_id
                 AND lead.conversation_id = conversation.id
                WHERE conversation.tenant_id = visit.tenant_id
                  AND conversation.company_id = visit.company_id
                  AND conversation.visit_id = visit.id
              )
              AND (
                SELECT count(message.id)
                FROM public.conversations AS conversation
                JOIN public.messages AS message
                  ON message.conversation_id = conversation.id
                 AND message.tenant_id = conversation.tenant_id
                 AND message.company_id = conversation.company_id
                WHERE conversation.tenant_id = visit.tenant_id
                  AND conversation.company_id = visit.company_id
                  AND conversation.visit_id = visit.id
                  AND message.role = 'user'
              ) < 3
              AND (
                SELECT count(action.id)
                FROM public.visit_events AS action
                WHERE action.tenant_id = visit.tenant_id
                  AND action.company_id = visit.company_id
                  AND action.visit_id = visit.id
                  AND action.event_type = 'cta_click'
              ) = 0
            ORDER BY visit.company_id
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
            'company',
            candidate.company_id,
            1,
            'visit.daily_digest.ready.v1',
            jsonb_build_object(
              'company_id', candidate.company_id::text,
              'digest_date', digest_day::text
            ),
            jsonb_build_object('contains_pii', false),
            'visit-daily-digest:' || candidate.company_id::text || ':' || digest_day::text,
            'pending'
          FROM candidate_companies AS candidate
          ON CONFLICT (tenant_id, company_id, deduplication_key) DO NOTHING;

          GET DIAGNOSTICS inserted_count = ROW_COUNT;
          RETURN inserted_count;
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.enqueue_visit_daily_digests(integer) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT EXECUTE ON FUNCTION
              app.enqueue_visit_daily_digests(integer)
              TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "REVOKE ALL ON FUNCTION app.enqueue_visit_daily_digests(integer) FROM PUBLIC"
    )
    op.execute("DROP FUNCTION app.enqueue_visit_daily_digests(integer)")
