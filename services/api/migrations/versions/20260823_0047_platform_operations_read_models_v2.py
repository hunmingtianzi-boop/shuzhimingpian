"""Upgrade platform operations read models to shared enterprise facts.

Revision ID: 20260823_0047
Revises: 20260823_0046
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260823_0047"
down_revision: str | None = "20260823_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_deterministic_uuid(
          p_seed text
        ) RETURNS uuid
        LANGUAGE sql
        IMMUTABLE
        PARALLEL SAFE
        SET search_path = pg_catalog
        AS $$
          SELECT (
            substr(md5(p_seed), 1, 8) || '-' ||
            substr(md5(p_seed), 9, 4) || '-' ||
            substr(md5(p_seed), 13, 4) || '-' ||
            substr(md5(p_seed), 17, 4) || '-' ||
            substr(md5(p_seed), 21, 12)
          )::uuid
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_task_rows(
          p_company_id uuid DEFAULT NULL,
          p_status text DEFAULT NULL,
          p_task_type text DEFAULT NULL,
          p_updated_from timestamptz DEFAULT NULL,
          p_updated_to timestamptz DEFAULT NULL
        ) RETURNS TABLE(
          id uuid,
          task_type text,
          business_label text,
          status text,
          company_id uuid,
          company_name text,
          tenant_slug text,
          error_code text,
          created_at timestamptz,
          updated_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
          WITH enterprise_companies AS (
            SELECT
              tenant.id AS tenant_id,
              tenant.slug AS tenant_slug,
              company.id AS company_id,
              company.name AS legal_name,
              company.short_name,
              company.status::text AS company_status,
              company.service_valid_until
            FROM public.companies AS company
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            WHERE tenant.type = 'enterprise'
              AND tenant.deleted_at IS NULL
              AND company.deleted_at IS NULL
              AND coalesce(tenant.settings ->> 'onboarding_status', '') <> 'provisional'
          ),
          onboarding_tasks AS (
            SELECT
              session.id,
              'onboarding'::text AS task_type,
              CASE session.status
                WHEN 'draft' THEN '待确认建企资料'
                WHEN 'processing' THEN '建企资料处理中'
                WHEN 'review' THEN '建企资料待复核'
                WHEN 'manual_required' THEN '建企资料需人工补全'
                WHEN 'ready_to_confirm' THEN '建企待最终确认'
                WHEN 'failed' THEN '建企处理失败'
                WHEN 'expired' THEN '建企任务已过期'
                ELSE '建企任务'
              END AS business_label,
              CASE session.status
                WHEN 'processing' THEN 'in_progress'
                WHEN 'manual_required' THEN 'blocked'
                WHEN 'failed' THEN 'failed'
                WHEN 'expired' THEN 'expired'
                ELSE 'pending'
              END AS status,
              ec.company_id,
              coalesce(ec.short_name, ec.legal_name) AS company_name,
              ec.tenant_slug,
              CASE
                WHEN session.status = 'failed' THEN 'ONBOARDING_FAILED'
                WHEN session.status = 'expired' THEN 'ONBOARDING_EXPIRED'
                ELSE NULL
              END AS error_code,
              session.created_at,
              session.updated_at
            FROM public.platform_onboarding_sessions AS session
            JOIN enterprise_companies AS ec ON ec.company_id = session.company_id
            WHERE session.purged_at IS NULL
              AND session.status IN (
                'draft', 'processing', 'review', 'manual_required',
                'ready_to_confirm', 'failed', 'expired'
              )
          ),
          knowledge_import_tasks AS (
            SELECT
              batch.id,
              'knowledge_import'::text AS task_type,
              '资料导入'::text AS business_label,
              CASE batch.status
                WHEN 'processing' THEN 'in_progress'
                WHEN 'failed' THEN 'failed'
                WHEN 'dead_letter' THEN 'failed'
                WHEN 'completed_with_errors' THEN 'failed'
                ELSE 'pending'
              END AS status,
              ec.company_id,
              coalesce(ec.short_name, ec.legal_name) AS company_name,
              ec.tenant_slug,
              CASE
                WHEN batch.status IN ('failed', 'dead_letter', 'completed_with_errors')
                  THEN 'IMPORT_FAILED'
                ELSE NULL
              END AS error_code,
              batch.created_at,
              batch.updated_at
            FROM public.knowledge_import_batches AS batch
            JOIN enterprise_companies AS ec ON ec.company_id = batch.company_id
            WHERE batch.status IN (
              'pending', 'processing', 'failed', 'dead_letter', 'completed_with_errors'
            )
          ),
          content_review_tasks AS (
            SELECT
              run.id,
              'content_review'::text AS task_type,
              '内容待审核'::text AS business_label,
              CASE
                WHEN run.status = 'failed' THEN 'failed'
                ELSE 'pending'
              END AS status,
              ec.company_id,
              coalesce(ec.short_name, ec.legal_name) AS company_name,
              ec.tenant_slug,
              CASE WHEN run.status = 'failed' THEN 'CONTENT_REVIEW_FAILED' ELSE NULL END,
              run.created_at,
              run.updated_at
            FROM public.content_import_runs AS run
            JOIN enterprise_companies AS ec ON ec.company_id = run.company_id
            WHERE EXISTS (
              SELECT 1
              FROM public.content_import_candidates AS candidate
              WHERE candidate.tenant_id = run.tenant_id
                AND candidate.company_id = run.company_id
                AND candidate.run_id = run.id
                AND candidate.status = 'pending_review'
            )
          ),
          enterprise_risk_tasks AS (
            SELECT
              app.platform_operations_deterministic_uuid(
                'enterprise-risk:' || ec.company_id::text
              ) AS id,
              'enterprise_risk'::text AS task_type,
              CASE
                WHEN ec.company_status = 'suspended' THEN '企业已暂停'
                ELSE '企业存在运营风险'
              END AS business_label,
              CASE
                WHEN ec.company_status = 'suspended' THEN 'blocked'
                ELSE 'pending'
              END AS status,
              ec.company_id,
              coalesce(ec.short_name, ec.legal_name) AS company_name,
              ec.tenant_slug,
              CASE
                WHEN ec.company_status = 'suspended' THEN 'ENTERPRISE_SUSPENDED'
                ELSE 'ENTERPRISE_RISK'
              END AS error_code,
              clock_timestamp() AS created_at,
              clock_timestamp() AS updated_at
            FROM enterprise_companies AS ec
            WHERE ec.company_status <> 'active'
          ),
          service_validity_tasks AS (
            SELECT
              app.platform_operations_deterministic_uuid(
                'service-validity:' || ec.company_id::text
              ) AS id,
              'service_validity'::text AS task_type,
              CASE
                WHEN ec.service_valid_until IS NULL THEN '服务有效期未配置'
                WHEN ec.service_valid_until < clock_timestamp() THEN '服务有效期已过期'
                ELSE '服务有效期临近到期'
              END AS business_label,
              CASE
                WHEN ec.service_valid_until < clock_timestamp() THEN 'failed'
                ELSE 'pending'
              END AS status,
              ec.company_id,
              coalesce(ec.short_name, ec.legal_name) AS company_name,
              ec.tenant_slug,
              CASE
                WHEN ec.service_valid_until IS NULL THEN 'SERVICE_VALIDITY_MISSING'
                WHEN ec.service_valid_until < clock_timestamp() THEN 'SERVICE_VALIDITY_EXPIRED'
                ELSE 'SERVICE_VALIDITY_WARNING'
              END AS error_code,
              clock_timestamp() AS created_at,
              clock_timestamp() AS updated_at
            FROM enterprise_companies AS ec
            WHERE ec.service_valid_until IS NULL
               OR ec.service_valid_until < clock_timestamp() + interval '30 days'
          ),
          combined AS (
            SELECT * FROM onboarding_tasks
            UNION ALL
            SELECT * FROM knowledge_import_tasks
            UNION ALL
            SELECT * FROM content_review_tasks
            UNION ALL
            SELECT * FROM enterprise_risk_tasks
            UNION ALL
            SELECT * FROM service_validity_tasks
          )
          SELECT *
          FROM combined
          WHERE (p_company_id IS NULL OR combined.company_id = p_company_id)
            AND (p_status IS NULL OR combined.status = p_status)
            AND (p_task_type IS NULL OR combined.task_type = p_task_type)
            AND (p_updated_from IS NULL OR combined.updated_at >= p_updated_from)
            AND (p_updated_to IS NULL OR combined.updated_at <= p_updated_to)
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_company_facts()
        RETURNS TABLE(
          tenant_id uuid,
          tenant_slug text,
          tenant_name text,
          company_id uuid,
          company_name text,
          legal_name text,
          short_name text,
          subject_type text,
          social_credit_code text,
          business_tenant_key text,
          status text,
          version integer,
          onboarding_status text,
          employee_count integer,
          card_count integer,
          published_card_count integer,
          visits_30d integer,
          unique_visitors_30d integer,
          conversations_30d integer,
          consented_leads_30d integer,
          profile_completion integer,
          actionable_task_count integer,
          failed_task_count integer,
          service_valid_until timestamptz,
          service_risk_level text,
          last_activity_at timestamptz,
          created_at timestamptz,
          updated_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
          WITH enterprise_companies AS (
            SELECT
              tenant.id AS tenant_id,
              tenant.slug AS tenant_slug,
              tenant.name AS tenant_name,
              company.id AS company_id,
              coalesce(company.short_name, company.name) AS company_name,
              company.name AS legal_name,
              company.short_name,
              company.subject_type,
              company.social_credit_code,
              company.business_tenant_key,
              company.status::text AS status,
              company.version,
              coalesce(company.settings ->> 'onboarding_status', 'content_pending')
                AS onboarding_status,
              company.service_valid_until,
              company.industry,
              company.settings,
              company.created_at,
              company.updated_at
            FROM public.companies AS company
            JOIN public.tenants AS tenant ON tenant.id = company.tenant_id
            WHERE tenant.type = 'enterprise'
              AND tenant.deleted_at IS NULL
              AND company.deleted_at IS NULL
              AND coalesce(tenant.settings ->> 'onboarding_status', '') <> 'provisional'
          ),
          membership_stats AS (
            SELECT
              membership.company_id,
              count(*) FILTER (WHERE membership.status = 'active')::integer AS employee_count
            FROM public.memberships AS membership
            GROUP BY membership.company_id
          ),
          card_stats AS (
            SELECT
              card.company_id,
              count(*) FILTER (WHERE card.deleted_at IS NULL)::integer AS card_count,
              count(*) FILTER (
                WHERE card.deleted_at IS NULL AND card.status = 'published'
              )::integer AS published_card_count,
              max(card.published_at) FILTER (
                WHERE card.deleted_at IS NULL AND card.status = 'published'
              ) AS last_published_card_at
            FROM public.cards AS card
            GROUP BY card.company_id
          ),
          visit_stats AS (
            SELECT
              visit.company_id,
              count(*) FILTER (
                WHERE visit.started_at >= clock_timestamp() - interval '30 days'
              )::integer AS visits_30d,
              count(DISTINCT visit.visitor_id) FILTER (
                WHERE visit.started_at >= clock_timestamp() - interval '30 days'
              )::integer AS unique_visitors_30d,
              max(visit.started_at) AS last_visit_at
            FROM public.visits AS visit
            GROUP BY visit.company_id
          ),
          conversation_stats AS (
            SELECT
              conversation.company_id,
              count(*) FILTER (
                WHERE conversation.started_at >= clock_timestamp() - interval '30 days'
              )::integer AS conversations_30d,
              max(conversation.started_at) AS last_conversation_at
            FROM public.conversations AS conversation
            GROUP BY conversation.company_id
          ),
          lead_stats AS (
            SELECT
              lead.company_id,
              count(*) FILTER (
                WHERE lead.created_at >= clock_timestamp() - interval '30 days'
              )::integer AS consented_leads_30d,
              max(lead.created_at) AS last_lead_at
            FROM public.leads AS lead
            GROUP BY lead.company_id
          ),
          task_stats AS (
            SELECT
              task.company_id,
              count(*) FILTER (
                WHERE task.status IN ('pending', 'in_progress', 'blocked', 'expired')
              )::integer AS actionable_task_count,
              count(*) FILTER (WHERE task.status = 'failed')::integer AS failed_task_count
            FROM app.platform_operations_task_rows(NULL, NULL, NULL, NULL, NULL) AS task
            GROUP BY task.company_id
          )
          SELECT
            ec.tenant_id,
            ec.tenant_slug,
            ec.tenant_name,
            ec.company_id,
            ec.company_name,
            ec.legal_name,
            ec.short_name,
            ec.subject_type,
            ec.social_credit_code,
            ec.business_tenant_key,
            ec.status,
            ec.version,
            ec.onboarding_status,
            coalesce(ms.employee_count, 0),
            coalesce(cs.card_count, 0),
            coalesce(cs.published_card_count, 0),
            coalesce(vs.visits_30d, 0),
            coalesce(vs.unique_visitors_30d, 0),
            coalesce(conv.conversations_30d, 0),
            coalesce(ls.consented_leads_30d, 0),
            (
              (CASE WHEN btrim(ec.legal_name) <> '' THEN 20 ELSE 0 END) +
              (
                CASE
                  WHEN nullif(btrim(coalesce(ec.short_name, '')), '') IS NOT NULL
                    THEN 10
                  ELSE 0
                END
              ) +
              (
                CASE
                  WHEN nullif(btrim(coalesce(ec.industry, '')), '') IS NOT NULL
                    THEN 15
                  ELSE 0
                END
              ) +
              (
                CASE
                  WHEN nullif(btrim(coalesce(ec.settings ->> 'summary', '')), '') IS NOT NULL
                    THEN 20
                  ELSE 0
                END
              ) +
              (
                CASE
                  WHEN nullif(btrim(coalesce(ec.settings ->> 'website', '')), '') IS NOT NULL
                    THEN 15
                  ELSE 0
                END
              ) +
              (
                CASE
                  WHEN nullif(btrim(coalesce(ec.settings ->> 'logo_url', '')), '') IS NOT NULL
                    THEN 20
                  ELSE 0
                END
              )
            )::integer AS profile_completion,
            coalesce(ts.actionable_task_count, 0),
            coalesce(ts.failed_task_count, 0),
            ec.service_valid_until,
            CASE
              WHEN ec.service_valid_until IS NULL THEN 'missing'
              WHEN ec.service_valid_until < clock_timestamp() THEN 'expired'
              WHEN ec.service_valid_until < clock_timestamp() + interval '30 days' THEN 'warning'
              ELSE 'healthy'
            END AS service_risk_level,
            greatest(
              coalesce(vs.last_visit_at, '-infinity'::timestamptz),
              coalesce(conv.last_conversation_at, '-infinity'::timestamptz),
              coalesce(ls.last_lead_at, '-infinity'::timestamptz),
              coalesce(cs.last_published_card_at, '-infinity'::timestamptz)
            ) AS last_activity_at,
            ec.created_at,
            ec.updated_at
          FROM enterprise_companies AS ec
          LEFT JOIN membership_stats AS ms ON ms.company_id = ec.company_id
          LEFT JOIN card_stats AS cs ON cs.company_id = ec.company_id
          LEFT JOIN visit_stats AS vs ON vs.company_id = ec.company_id
          LEFT JOIN conversation_stats AS conv ON conv.company_id = ec.company_id
          LEFT JOIN lead_stats AS ls ON ls.company_id = ec.company_id
          LEFT JOIN task_stats AS ts ON ts.company_id = ec.company_id
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_overview() RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;

          WITH facts AS (
            SELECT * FROM app.platform_operations_company_facts()
          )
          SELECT jsonb_build_object(
            'generated_at', clock_timestamp(),
            'enabled_enterprise_count', count(*) FILTER (WHERE facts.status = 'active'),
            'active_enterprise_30d_count', count(*) FILTER (
              WHERE facts.last_activity_at >= clock_timestamp() - interval '30 days'
            ),
            'pending_activation_count', count(*) FILTER (
              WHERE facts.onboarding_status <> 'completed'
            ),
            'published_card_count', coalesce(sum(facts.published_card_count), 0),
            'visits_30d', coalesce(sum(facts.visits_30d), 0),
            'unique_visitors_30d', coalesce(sum(facts.unique_visitors_30d), 0),
            'conversations_30d', coalesce(sum(facts.conversations_30d), 0),
            'consented_leads_30d', coalesce(sum(facts.consented_leads_30d), 0),
            'pending_task_count', coalesce(
              (SELECT count(*) FROM app.platform_operations_task_rows(
                NULL, 'pending', NULL, NULL, NULL
              )), 0
            ),
            'failed_task_count', coalesce(
              (SELECT count(*) FROM app.platform_operations_task_rows(
                NULL, 'failed', NULL, NULL, NULL
              )), 0
            ),
            'service_risk_count', count(*) FILTER (
              WHERE facts.service_risk_level IN ('warning', 'expired', 'missing')
            ),
            'llm_ready', EXISTS (
              SELECT 1
              FROM public.platform_llm_profiles AS profile
              WHERE profile.enabled AND profile.is_active
            ),
            'import_ready', to_regclass('public.knowledge_import_batches') IS NOT NULL
          ) INTO result
          FROM facts;

          RETURN result;
        END
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_enterprises(
          p_search text,
          p_status text,
          p_activity_level text,
          p_has_actionable_tasks boolean,
          p_service_risk text,
          p_sort_by text,
          p_sort_order text,
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          result jsonb;
          normalized_search text := nullif(btrim(p_search), '');
          normalized_status text := nullif(btrim(p_status), '');
          normalized_activity text := nullif(btrim(p_activity_level), '');
          normalized_risk text := nullif(btrim(p_service_risk), '');
          normalized_sort_by text := coalesce(nullif(btrim(p_sort_by), ''), 'created_at');
          normalized_sort_order text := coalesce(nullif(btrim(p_sort_order), ''), 'desc');
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;
          IF p_limit IS NULL OR p_offset IS NULL
             OR p_limit < 1 OR p_limit > 100 OR p_offset < 0 THEN
            RAISE EXCEPTION 'invalid platform enterprise pagination'
              USING ERRCODE = '22023';
          END IF;

          WITH matching AS (
            SELECT * FROM app.platform_operations_company_facts() AS facts
            WHERE (
                normalized_search IS NULL
                OR strpos(lower(facts.tenant_name), lower(normalized_search)) > 0
                OR strpos(lower(facts.tenant_slug), lower(normalized_search)) > 0
                OR strpos(lower(facts.legal_name), lower(normalized_search)) > 0
                OR strpos(lower(coalesce(facts.short_name, '')), lower(normalized_search)) > 0
                OR strpos(lower(facts.business_tenant_key), lower(normalized_search)) > 0
              )
              AND (normalized_status IS NULL OR facts.status = normalized_status)
              AND (
                normalized_activity IS NULL
                OR (
                  normalized_activity = 'active_30d'
                  AND facts.last_activity_at >= clock_timestamp() - interval '30 days'
                )
                OR (
                  normalized_activity = 'inactive_30d'
                  AND (
                    facts.last_activity_at IS NULL
                    OR facts.last_activity_at < clock_timestamp() - interval '30 days'
                  )
                )
              )
              AND (
                p_has_actionable_tasks IS NULL
                OR (p_has_actionable_tasks IS TRUE AND facts.actionable_task_count > 0)
                OR (p_has_actionable_tasks IS FALSE AND facts.actionable_task_count = 0)
              )
              AND (normalized_risk IS NULL OR facts.service_risk_level = normalized_risk)
          ),
          page AS (
            SELECT * FROM matching
            ORDER BY
              CASE
                WHEN normalized_sort_by = 'company_name' AND normalized_sort_order = 'asc'
                  THEN company_name
              END ASC,
              CASE
                WHEN normalized_sort_by = 'company_name' AND normalized_sort_order = 'desc'
                  THEN company_name
              END DESC,
              CASE
                WHEN normalized_sort_by = 'created_at' AND normalized_sort_order = 'asc'
                  THEN created_at
              END ASC,
              CASE
                WHEN normalized_sort_by = 'created_at' AND normalized_sort_order = 'desc'
                  THEN created_at
              END DESC,
              CASE
                WHEN normalized_sort_by = 'last_activity_at' AND normalized_sort_order = 'asc'
                  THEN last_activity_at
              END ASC,
              CASE
                WHEN normalized_sort_by = 'last_activity_at' AND normalized_sort_order = 'desc'
                  THEN last_activity_at
              END DESC,
              CASE
                WHEN normalized_sort_by = 'visits_30d' AND normalized_sort_order = 'asc'
                  THEN visits_30d
              END ASC,
              CASE
                WHEN normalized_sort_by = 'visits_30d' AND normalized_sort_order = 'desc'
                  THEN visits_30d
              END DESC,
              CASE
                WHEN normalized_sort_by = 'conversations_30d' AND normalized_sort_order = 'asc'
                  THEN conversations_30d
              END ASC,
              CASE
                WHEN normalized_sort_by = 'conversations_30d' AND normalized_sort_order = 'desc'
                  THEN conversations_30d
              END DESC,
              CASE
                WHEN normalized_sort_by = 'consented_leads_30d' AND normalized_sort_order = 'asc'
                  THEN consented_leads_30d
              END ASC,
              CASE
                WHEN normalized_sort_by = 'consented_leads_30d' AND normalized_sort_order = 'desc'
                  THEN consented_leads_30d
              END DESC,
              CASE
                WHEN normalized_sort_by = 'actionable_task_count' AND normalized_sort_order = 'asc'
                  THEN actionable_task_count
              END ASC,
              CASE
                WHEN normalized_sort_by = 'actionable_task_count' AND normalized_sort_order = 'desc'
                  THEN actionable_task_count
              END DESC,
              CASE
                WHEN normalized_sort_by = 'service_valid_until' AND normalized_sort_order = 'asc'
                  THEN service_valid_until
              END ASC NULLS LAST,
              CASE
                WHEN normalized_sort_by = 'service_valid_until' AND normalized_sort_order = 'desc'
                  THEN service_valid_until
              END DESC NULLS LAST,
              created_at DESC,
              company_id DESC
            LIMIT p_limit OFFSET p_offset
          )
          SELECT jsonb_build_object(
            'data', coalesce(
              (SELECT jsonb_agg(to_jsonb(row)) FROM page AS row),
              '[]'::jsonb
            ),
            'total', (SELECT count(*) FROM matching)
          ) INTO result;
          RETURN result;
        END
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_enterprise_detail(
          p_company_id uuid,
          p_public_card_base_url text
        ) RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          result jsonb;
          normalized_base_url text := rtrim(p_public_card_base_url, '/');
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;

          WITH target AS (
            SELECT * FROM app.platform_operations_company_facts()
            WHERE company_id = p_company_id
          )
          SELECT jsonb_build_object(
            'tenant_id', target.tenant_id,
            'tenant_slug', target.tenant_slug,
            'tenant_name', target.tenant_name,
            'company_id', target.company_id,
            'company_name', target.company_name,
            'legal_name', target.legal_name,
            'short_name', target.short_name,
            'subject_type', target.subject_type,
            'social_credit_code', target.social_credit_code,
            'business_tenant_key', target.business_tenant_key,
            'status', target.status,
            'version', target.version,
            'onboarding_status', target.onboarding_status,
            'profile_completion', target.profile_completion,
            'employee_count', target.employee_count,
            'card_count', target.card_count,
            'published_card_count', target.published_card_count,
            'visits_30d', target.visits_30d,
            'unique_visitors_30d', target.unique_visitors_30d,
            'conversations_30d', target.conversations_30d,
            'consented_leads_30d', target.consented_leads_30d,
            'actionable_task_count', target.actionable_task_count,
            'failed_task_count', target.failed_task_count,
            'service_valid_until', target.service_valid_until,
            'service_risk_level', target.service_risk_level,
            'last_activity_at', target.last_activity_at,
            'cards', coalesce(
              (
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'id', card.id,
                    'display_name', card.display_name,
                    'title', coalesce(card.settings ->> 'title', ''),
                    'status', card.status::text,
                    'updated_at', card.updated_at,
                    'share_url', CASE
                      WHEN card.status = 'published'
                        THEN normalized_base_url || '/c/' || card.slug
                      ELSE NULL
                    END
                  )
                  ORDER BY card.updated_at DESC, card.id DESC
                )
                FROM public.cards AS card
                WHERE card.company_id = target.company_id
                  AND card.deleted_at IS NULL
              ),
              '[]'::jsonb
            ),
            'recent_tasks', coalesce(
              (
                SELECT jsonb_agg(to_jsonb(task))
                FROM (
                  SELECT *
                  FROM app.platform_operations_task_rows(
                    target.company_id, NULL, NULL, NULL, NULL
                  )
                  ORDER BY updated_at DESC, id DESC
                  LIMIT 10
                ) AS task
              ),
              '[]'::jsonb
            ),
            'created_at', target.created_at,
            'updated_at', target.updated_at
          ) INTO result
          FROM target;

          RETURN result;
        END
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_company_aggregates(
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;

          WITH matching AS (
            SELECT * FROM app.platform_operations_company_facts()
          ),
          page AS (
            SELECT * FROM matching
            ORDER BY company_name, company_id
            LIMIT p_limit OFFSET p_offset
          )
          SELECT jsonb_build_object(
            'data', coalesce(
              (SELECT jsonb_agg(to_jsonb(row)) FROM page AS row),
              '[]'::jsonb
            ),
            'total', (SELECT count(*) FROM matching)
          ) INTO result;
          RETURN result;
        END
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_tasks(
          p_company_id uuid,
          p_status text,
          p_task_type text,
          p_updated_from timestamptz,
          p_updated_to timestamptz,
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;

          WITH matching AS (
            SELECT *
            FROM app.platform_operations_task_rows(
              p_company_id, p_status, p_task_type, p_updated_from, p_updated_to
            )
          ),
          page AS (
            SELECT * FROM matching
            ORDER BY updated_at DESC, id DESC
            LIMIT p_limit OFFSET p_offset
          )
          SELECT jsonb_build_object(
            'data', coalesce(
              (SELECT jsonb_agg(to_jsonb(row)) FROM page AS row),
              '[]'::jsonb
            ),
            'total', (SELECT count(*) FROM matching)
          ) INTO result;
          RETURN result;
        END
        $$;
        """
    )
    op.execute(
        r"""
        CREATE OR REPLACE FUNCTION app.platform_operations_task_groups(
          p_company_id uuid,
          p_status text,
          p_task_type text,
          p_updated_from timestamptz,
          p_updated_to timestamptz,
          p_limit integer,
          p_offset integer
        ) RETURNS jsonb
        LANGUAGE plpgsql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE result jsonb;
        BEGIN
          IF NOT app.platform_actor_allowed() THEN
            RAISE EXCEPTION 'platform administrator session required'
              USING ERRCODE = '42501';
          END IF;

          WITH matching AS (
            SELECT *
            FROM app.platform_operations_task_rows(
              p_company_id, p_status, p_task_type, p_updated_from, p_updated_to
            )
          ),
          grouped AS (
            SELECT
              task.company_id,
              max(task.company_name) AS company_name,
              count(*) FILTER (WHERE task.status = 'pending')::integer AS pending_count,
              count(*) FILTER (WHERE task.status = 'in_progress')::integer AS in_progress_count,
              count(*) FILTER (WHERE task.status = 'failed')::integer AS failed_count
            FROM matching AS task
            GROUP BY task.company_id
            ORDER BY max(task.company_name), task.company_id
            LIMIT p_limit OFFSET p_offset
          )
          SELECT jsonb_build_object(
            'groups', coalesce(
              (
                SELECT jsonb_agg(
                  jsonb_build_object(
                    'company_id', group_row.company_id,
                    'company_name', group_row.company_name,
                    'pending_count', group_row.pending_count,
                    'in_progress_count', group_row.in_progress_count,
                    'failed_count', group_row.failed_count,
                    'recent_tasks', coalesce(
                      (
                        SELECT jsonb_agg(to_jsonb(task_row))
                        FROM (
                          SELECT *
                          FROM matching AS inner_task
                          WHERE inner_task.company_id = group_row.company_id
                          ORDER BY inner_task.updated_at DESC, inner_task.id DESC
                          LIMIT 5
                        ) AS task_row
                      ),
                      '[]'::jsonb
                    )
                  )
                )
                FROM grouped AS group_row
              ),
              '[]'::jsonb
            ),
            'total', (SELECT count(DISTINCT company_id) FROM matching)
          ) INTO result;
          RETURN result;
        END
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_task_rows("
        "uuid, text, text, timestamptz, timestamptz"
        ") FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.platform_operations_company_facts() FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.platform_operations_task_groups("
        "uuid, text, text, timestamptz, timestamptz, integer, integer"
        ") FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'cf_ai_card_app'
          ) THEN
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_deterministic_uuid(text)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_task_rows(uuid, text, text, timestamptz, timestamptz)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_company_facts()
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION
              app.platform_operations_task_groups(
                uuid, text, text, timestamptz, timestamptz, integer, integer
              ) TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "app.platform_operations_task_groups("
        "uuid, text, text, timestamptz, timestamptz, integer, integer)"
    )
    op.execute("DROP FUNCTION IF EXISTS app.platform_operations_company_facts()")
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "app.platform_operations_task_rows(uuid, text, text, timestamptz, timestamptz)"
    )
    op.execute("DROP FUNCTION IF EXISTS app.platform_operations_deterministic_uuid(text)")
