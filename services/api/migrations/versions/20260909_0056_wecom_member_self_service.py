"""Provision verified WeCom members inside an existing enterprise.

Revision ID: 20260909_0056
Revises: 20260901_0055
"""

from alembic import op

revision = "20260909_0056"
down_revision = "20260901_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION app.provision_wecom_member(
          p_corp_id_hmac text,
          p_wecom_user_id_hmac text,
          p_wecom_user_id_ciphertext bytea,
          p_profile_ciphertext bytea,
          p_encryption_key_ref text,
          p_display_name text,
          p_password_hash text
        )
        RETURNS TABLE (
          user_id uuid, membership_id uuid, tenant_id uuid,
          company_id uuid, created boolean
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
        BEGIN
          IF p_corp_id_hmac IS NULL OR length(p_corp_id_hmac) <> 64
             OR p_wecom_user_id_hmac IS NULL OR length(p_wecom_user_id_hmac) <> 64
             OR p_wecom_user_id_ciphertext IS NULL
             OR p_profile_ciphertext IS NULL
             OR p_encryption_key_ref IS NULL
             OR length(btrim(p_encryption_key_ref)) NOT BETWEEN 1 AND 128
             OR p_display_name IS NULL
             OR length(btrim(p_display_name)) NOT BETWEEN 1 AND 120
             OR p_password_hash IS NULL OR length(p_password_hash) < 32
          THEN
            RAISE EXCEPTION 'invalid WeCom member input' USING ERRCODE = '22023';
          END IF;

          -- Share the bootstrap lock so concurrent first logins are idempotent.
          PERFORM pg_advisory_xact_lock(
            hashtextextended('wecom-enterprise:' || p_corp_id_hmac, 0)
          );
          SELECT * INTO v_scope FROM public.wecom_enterprise_scopes
          WHERE corp_id_hmac = p_corp_id_hmac;
          IF NOT FOUND THEN RETURN; END IF;

          RETURN QUERY
          SELECT r.user_id, r.membership_id, r.tenant_id, r.company_id, false
          FROM app.resolve_wecom_identity(p_corp_id_hmac, p_wecom_user_id_hmac) AS r;
          IF FOUND THEN RETURN; END IF;

          -- A revoked/disabled identity must never be recreated by OAuth login.
          IF EXISTS (
            SELECT 1 FROM public.wecom_user_bindings AS binding
            WHERE binding.corp_id_hmac = p_corp_id_hmac
              AND binding.wecom_user_id_hmac = p_wecom_user_id_hmac
          ) OR NOT EXISTS (
            SELECT 1 FROM public.tenants AS tenant
            JOIN public.companies AS company ON company.tenant_id = tenant.id
            WHERE tenant.id = v_scope.tenant_id AND company.id = v_scope.company_id
              AND tenant.status = 'active' AND tenant.deleted_at IS NULL
              AND company.status = 'active' AND company.deleted_at IS NULL
          ) THEN
            RAISE EXCEPTION 'WeCom account or enterprise is disabled'
              USING ERRCODE = 'P0001';
          END IF;

          INSERT INTO public.users (id, display_name, status)
          VALUES (v_user_id, btrim(p_display_name), 'active');
          INSERT INTO public.memberships (
            id, user_id, tenant_id, company_id, role, permissions, status
          ) VALUES (
            v_membership_id, v_user_id, v_scope.tenant_id, v_scope.company_id,
            'card_owner',
            ARRAY['analytics.read', 'card.read', 'card.write', 'catalog.read',
                  'conversations.read', 'leads.read', 'leads.write']::varchar[],
            'active'
          );
          -- No usable password is distributed; this keeps member management
          -- compatible while the member signs in exclusively through WeCom.
          INSERT INTO public.staff_credentials (
            user_id, membership_id, tenant_id, company_id,
            account_normalized, password_hash, is_enabled
          ) VALUES (
            v_user_id, v_membership_id, v_scope.tenant_id, v_scope.company_id,
            'wecom-' || p_wecom_user_id_hmac, p_password_hash, true
          );
          INSERT INTO public.wecom_user_bindings (
            tenant_id, company_id, user_id, membership_id, corp_id_hmac,
            wecom_user_id_ciphertext, wecom_user_id_hmac,
            profile_ciphertext, encryption_key_ref, last_synced_at
          ) VALUES (
            v_scope.tenant_id, v_scope.company_id, v_user_id, v_membership_id,
            p_corp_id_hmac, p_wecom_user_id_ciphertext, p_wecom_user_id_hmac,
            p_profile_ciphertext, p_encryption_key_ref, now()
          );
          RETURN QUERY SELECT v_user_id, v_membership_id,
            v_scope.tenant_id, v_scope.company_id, true;
        END
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION app.provision_wecom_member("
        "text, text, bytea, bytea, text, text, text) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT EXECUTE ON FUNCTION app.provision_wecom_member(
              text, text, bytea, bytea, text, text, text
            ) TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS app.provision_wecom_member("
        "text, text, bytea, bytea, text, text, text)"
    )
