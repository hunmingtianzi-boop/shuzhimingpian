"""Independent Official Account identities and private card-owner workspaces.

Revision ID: 20260921_0057
Revises: 20260909_0056
"""

from alembic import op

revision = "20260921_0057"
down_revision = "20260909_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Global identity routing is only accessible through the narrow function;
    # business data continues to use existing forced tenant/company RLS.
    op.execute("""
        CREATE TABLE wechat_accounts (
          identity_hmac varchar(64) PRIMARY KEY CHECK (length(identity_hmac) = 64),
          openid_ciphertext bytea NOT NULL,
          encryption_key_ref varchar(128) NOT NULL,
          user_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
          membership_id uuid NOT NULL UNIQUE REFERENCES memberships(id) ON DELETE RESTRICT,
          tenant_id uuid NOT NULL,
          company_id uuid NOT NULL,
          revoked_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          FOREIGN KEY (tenant_id, company_id)
            REFERENCES companies(tenant_id, id) ON DELETE RESTRICT
        );
    """)
    op.execute("REVOKE ALL ON TABLE wechat_accounts FROM PUBLIC")
    op.execute(r"""
        CREATE FUNCTION app.provision_wechat_account(
          p_identity_hmac text, p_openid_ciphertext bytea,
          p_key_ref text, p_password_hash text
        ) RETURNS TABLE (user_id uuid, membership_id uuid, tenant_id uuid, company_id uuid)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          v_account public.wechat_accounts%ROWTYPE;
          v_user uuid := gen_random_uuid();
          v_member uuid := gen_random_uuid();
          v_tenant uuid := gen_random_uuid();
          v_company uuid := gen_random_uuid();
          v_card uuid := gen_random_uuid();
          v_slug text := 'wx-' || replace(gen_random_uuid()::text, '-', '');
        BEGIN
          IF p_identity_hmac IS NULL OR p_identity_hmac !~ '^[0-9a-f]{64}$'
             OR p_openid_ciphertext IS NULL OR octet_length(p_openid_ciphertext) = 0
             OR p_key_ref IS NULL OR length(btrim(p_key_ref)) NOT BETWEEN 1 AND 128
             OR p_password_hash IS NULL OR length(p_password_hash) < 32 THEN
            RAISE EXCEPTION 'invalid WeChat identity' USING ERRCODE = '22023';
          END IF;
          PERFORM pg_advisory_xact_lock(hashtextextended('wechat:' || p_identity_hmac, 0));
          SELECT * INTO v_account FROM public.wechat_accounts
            WHERE identity_hmac = p_identity_hmac;
          IF FOUND THEN
            IF v_account.revoked_at IS NOT NULL OR NOT EXISTS (
              SELECT 1 FROM public.memberships AS m
              JOIN public.users AS u ON u.id = m.user_id
              JOIN public.tenants AS t ON t.id = m.tenant_id
              JOIN public.companies AS c ON c.id = m.company_id AND c.tenant_id = m.tenant_id
              WHERE m.id = v_account.membership_id AND m.user_id = v_account.user_id
                AND m.tenant_id = v_account.tenant_id AND m.company_id = v_account.company_id
                AND m.status = 'active' AND u.status = 'active' AND u.deleted_at IS NULL
                AND t.status = 'active' AND t.deleted_at IS NULL
                AND c.status = 'active' AND c.deleted_at IS NULL
            ) THEN
              RAISE EXCEPTION 'WeChat account disabled' USING ERRCODE = 'P0001';
            END IF;
            RETURN QUERY SELECT v_account.user_id, v_account.membership_id,
              v_account.tenant_id, v_account.company_id;
            RETURN;
          END IF;

          -- A private storage scope, not membership of any existing enterprise.
          INSERT INTO public.tenants (id, slug, name, type, status, settings)
          VALUES (v_tenant, v_slug, '我的名片空间', 'enterprise', 'active',
            jsonb_build_object('provisioned_via', 'wechat_oauth', 'workspace_kind', 'personal'));
          INSERT INTO public.users (id, display_name, status)
          VALUES (v_user, '微信用户', 'active');
          INSERT INTO public.companies (id, tenant_id, name, normalized_name, status, settings)
          VALUES (v_company, v_tenant, '个人名片', '个人名片', 'active',
            jsonb_build_object('provisioned_via', 'wechat_oauth', 'workspace_kind', 'personal',
              'summary', '', 'policy_versions', jsonb_build_object(
                'profile_personalization', 'profile-personalization-v1')));
          INSERT INTO public.memberships
            (id, user_id, tenant_id, company_id, role, permissions, status)
          VALUES (v_member, v_user, v_tenant, v_company, 'card_owner',
            ARRAY['analytics.read', 'card.read', 'card.write', 'catalog.read',
                  'conversations.read', 'leads.read', 'leads.write']::varchar[], 'active');
          INSERT INTO public.staff_credentials (user_id, membership_id, tenant_id, company_id,
            account_normalized, password_hash, is_enabled, must_change_password)
          VALUES (v_user, v_member, v_tenant, v_company,
            'wechat-' || p_identity_hmac, p_password_hash, true, false);
          INSERT INTO public.cards (id, tenant_id, company_id, card_kind, owner_user_id,
            responsible_user_id, slug, display_name, status, settings)
          VALUES (v_card, v_tenant, v_company, 'employee', v_user, v_user,
            v_slug, '微信用户', 'draft', jsonb_build_object(
              'title', '', 'assistant_name', '名片助手',
              'welcome_message', '您好，欢迎了解我的名片。',
              'suggested_questions', jsonb_build_array(),
              'policy_versions', jsonb_build_object('privacy', 'privacy-v1',
                'chat_notice', 'chat-notice-v1', 'lead_consent', 'lead-consent-v1',
                'profile_personalization', 'profile-personalization-v1')));
          INSERT INTO public.wechat_accounts (identity_hmac, openid_ciphertext, encryption_key_ref,
            user_id, membership_id, tenant_id, company_id)
          VALUES (p_identity_hmac, p_openid_ciphertext, p_key_ref, v_user, v_member,
            v_tenant, v_company);
          RETURN QUERY SELECT v_user, v_member, v_tenant, v_company;
        END
        $$;
    """)
    op.execute(
        "REVOKE ALL ON FUNCTION app.provision_wechat_account(text, bytea, text, text) FROM PUBLIC"
    )
    op.execute("""
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            REVOKE ALL ON TABLE wechat_accounts FROM cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.provision_wechat_account(text, bytea, text, text)
              TO cf_ai_card_app;
          END IF;
        END
        $grant$;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.provision_wechat_account(text, bytea, text, text)")
    op.execute("DROP TABLE IF EXISTS wechat_accounts")
