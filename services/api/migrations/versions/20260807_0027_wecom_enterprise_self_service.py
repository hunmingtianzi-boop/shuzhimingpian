"""Allow an authenticated WeCom corporation to bootstrap its enterprise scope.

Revision ID: 20260807_0027
Revises: 20260801_0026
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260807_0027"
down_revision = "20260801_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wecom_enterprise_scopes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("corp_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provisioned_by_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "char_length(corp_id_hmac) = 64",
            name="corp_id_hmac_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provisioned_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "corp_id_hmac",
            name="uq_wecom_enterprise_scopes_corp",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            name="uq_wecom_enterprise_scopes_scope",
        ),
    )
    op.execute(
        "CREATE TRIGGER trg_wecom_enterprise_scopes_touch_updated_at "
        "BEFORE UPDATE ON wecom_enterprise_scopes "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    # This table is a global provider-to-scope index.  It is never granted to
    # the runtime role directly; the two narrowly-scoped functions below are
    # the only supported access path.
    op.execute("REVOKE ALL ON TABLE wecom_enterprise_scopes FROM PUBLIC")

    op.execute(
        r"""
        CREATE FUNCTION app.resolve_wecom_identity(
          p_corp_id_hmac text,
          p_wecom_user_id_hmac text
        )
        RETURNS TABLE (
          user_id uuid,
          membership_id uuid,
          tenant_id uuid,
          company_id uuid
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
          SELECT binding.user_id,
                 binding.membership_id,
                 binding.tenant_id,
                 binding.company_id
          FROM public.wecom_enterprise_scopes AS scope
          JOIN public.wecom_user_bindings AS binding
            ON binding.tenant_id = scope.tenant_id
           AND binding.company_id = scope.company_id
           AND binding.corp_id_hmac = scope.corp_id_hmac
          JOIN public.memberships AS membership
            ON membership.id = binding.membership_id
           AND membership.user_id = binding.user_id
           AND membership.tenant_id = binding.tenant_id
           AND membership.company_id = binding.company_id
          JOIN public.users AS staff ON staff.id = binding.user_id
          JOIN public.tenants AS tenant ON tenant.id = binding.tenant_id
          JOIN public.companies AS company
            ON company.id = binding.company_id
           AND company.tenant_id = binding.tenant_id
          WHERE length(p_corp_id_hmac) = 64
            AND length(p_wecom_user_id_hmac) = 64
            AND scope.corp_id_hmac = p_corp_id_hmac
            AND binding.wecom_user_id_hmac = p_wecom_user_id_hmac
            AND binding.revoked_at IS NULL
            AND membership.status = 'active'
            AND staff.status = 'active'
            AND staff.deleted_at IS NULL
            AND tenant.status = 'active'
            AND tenant.deleted_at IS NULL
            AND company.status = 'active'
            AND company.deleted_at IS NULL
          LIMIT 1
        $$
        """
    )

    op.execute(
        r"""
        CREATE FUNCTION app.bootstrap_wecom_enterprise(
          p_corp_id_hmac text,
          p_wecom_user_id_hmac text,
          p_wecom_user_id_ciphertext bytea,
          p_profile_ciphertext bytea,
          p_encryption_key_ref text,
          p_enterprise_name text,
          p_admin_display_name text,
          p_tenant_slug text,
          p_card_slug text
        )
        RETURNS TABLE (
          user_id uuid,
          membership_id uuid,
          tenant_id uuid,
          company_id uuid,
          created boolean
        )
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          v_scope public.wecom_enterprise_scopes%ROWTYPE;
          v_user_id uuid := gen_random_uuid();
          v_membership_id uuid := gen_random_uuid();
          v_tenant_id uuid := gen_random_uuid();
          v_company_id uuid := gen_random_uuid();
          v_card_id uuid := gen_random_uuid();
          v_binding_id uuid := gen_random_uuid();
          v_name text := btrim(p_enterprise_name);
          v_display_name text := btrim(p_admin_display_name);
        BEGIN
          IF length(p_corp_id_hmac) <> 64
             OR length(p_wecom_user_id_hmac) <> 64
             OR p_wecom_user_id_ciphertext IS NULL
             OR p_profile_ciphertext IS NULL
             OR length(btrim(p_encryption_key_ref)) NOT BETWEEN 1 AND 128
             OR length(v_name) NOT BETWEEN 1 AND 200
             OR length(v_display_name) NOT BETWEEN 1 AND 120
             OR p_tenant_slug !~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'
             OR p_card_slug !~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'
          THEN
            RAISE EXCEPTION 'invalid WeCom bootstrap input'
              USING ERRCODE = '22023';
          END IF;

          PERFORM pg_advisory_xact_lock(
            hashtextextended('wecom-enterprise:' || p_corp_id_hmac, 0)
          );

          SELECT * INTO v_scope
          FROM public.wecom_enterprise_scopes
          WHERE corp_id_hmac = p_corp_id_hmac;

          IF FOUND THEN
            RETURN QUERY
            SELECT resolved.user_id,
                   resolved.membership_id,
                   resolved.tenant_id,
                   resolved.company_id,
                   false
            FROM app.resolve_wecom_identity(
              p_corp_id_hmac,
              p_wecom_user_id_hmac
            ) AS resolved;
            RETURN;
          END IF;

          INSERT INTO public.tenants (
            id, slug, name, type, status, settings
          ) VALUES (
            v_tenant_id,
            p_tenant_slug,
            v_name,
            'enterprise',
            'active',
            jsonb_build_object(
              'slug', p_tenant_slug,
              'onboarding_status', 'content_pending',
              'provisioned_via', 'wecom_oauth'
            )
          );
          INSERT INTO public.users (
            id, display_name, status
          ) VALUES (
            v_user_id, v_display_name, 'active'
          );
          INSERT INTO public.companies (
            id, tenant_id, name, normalized_name, status, settings
          ) VALUES (
            v_company_id,
            v_tenant_id,
            v_name,
            lower(regexp_replace(v_name, '\s+', ' ', 'g')),
            'active',
            jsonb_build_object(
              'summary', '',
              'website', NULL,
              'logo_url', NULL,
              'onboarding_status', 'content_pending',
              'provisioned_via', 'wecom_oauth',
              'policy_versions', jsonb_build_object(
                'profile_personalization', 'profile-personalization-v1'
              )
            )
          );
          INSERT INTO public.memberships (
            id, user_id, tenant_id, company_id, role, permissions, status
          ) VALUES (
            v_membership_id,
            v_user_id,
            v_tenant_id,
            v_company_id,
            'company_admin',
            ARRAY[
              'company.manage', 'card.manage', 'knowledge.manage',
              'knowledge.publish', 'catalog.manage', 'conversations.read',
              'summaries.write', 'leads.read', 'leads.write',
              'privacy.manage', 'analytics.read'
            ]::varchar[],
            'active'
          );
          INSERT INTO public.cards (
            id, tenant_id, company_id, card_kind, owner_user_id,
            responsible_user_id, slug, display_name, status, settings
          ) VALUES (
            v_card_id,
            v_tenant_id,
            v_company_id,
            'enterprise',
            NULL,
            v_user_id,
            p_card_slug,
            v_name,
            'draft',
            jsonb_build_object(
              'title', v_name,
              'assistant_name', '企业 AI 接待',
              'welcome_message', '您好，我可以根据企业已审核资料为您介绍业务。',
              'suggested_questions', jsonb_build_array(),
              'onboarding_status', 'content_pending',
              'policy_versions', jsonb_build_object(
                'privacy', 'privacy-v1',
                'chat_notice', 'chat-notice-v1',
                'lead_consent', 'lead-consent-v1',
                'profile_personalization', 'profile-personalization-v1'
              )
            )
          );
          INSERT INTO public.wecom_user_bindings (
            id, tenant_id, company_id, user_id, membership_id,
            corp_id_hmac, wecom_user_id_ciphertext, wecom_user_id_hmac,
            profile_ciphertext, encryption_key_ref, last_synced_at
          ) VALUES (
            v_binding_id,
            v_tenant_id,
            v_company_id,
            v_user_id,
            v_membership_id,
            p_corp_id_hmac,
            p_wecom_user_id_ciphertext,
            p_wecom_user_id_hmac,
            p_profile_ciphertext,
            p_encryption_key_ref,
            now()
          );
          INSERT INTO public.wecom_enterprise_scopes (
            corp_id_hmac, tenant_id, company_id, provisioned_by_user_id
          ) VALUES (
            p_corp_id_hmac, v_tenant_id, v_company_id, v_user_id
          );
          INSERT INTO public.outbox_events (
            tenant_id, company_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload, headers,
            deduplication_key, status
          ) VALUES (
            v_tenant_id,
            v_company_id,
            'company',
            v_company_id,
            1,
            'enterprise.created.v1',
            jsonb_build_object(
              'tenant_id', v_tenant_id,
              'company_id', v_company_id,
              'admin_user_id', v_user_id,
              'source', 'wecom_oauth'
            ),
            jsonb_build_object('contains_pii', false),
            'enterprise.created:' || v_company_id::text,
            'pending'
          );

          RETURN QUERY SELECT
            v_user_id,
            v_membership_id,
            v_tenant_id,
            v_company_id,
            true;
        END
        $$
        """
    )

    op.execute(
        "REVOKE ALL ON FUNCTION app.resolve_wecom_identity(text, text) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.bootstrap_wecom_enterprise("
        "text, text, bytea, bytea, text, text, text, text, text) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT EXECUTE ON FUNCTION app.resolve_wecom_identity(text, text)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.bootstrap_wecom_enterprise(
              text, text, bytea, bytea, text, text, text, text, text
            ) TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS app.bootstrap_wecom_enterprise("
        "text, text, bytea, bytea, text, text, text, text, text)"
    )
    op.execute("DROP FUNCTION IF EXISTS app.resolve_wecom_identity(text, text)")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_wecom_enterprise_scopes_touch_updated_at "
        "ON wecom_enterprise_scopes"
    )
    op.drop_table("wecom_enterprise_scopes")
