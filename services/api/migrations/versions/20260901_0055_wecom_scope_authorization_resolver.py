"""Resolve a WeCom provider authorization from an exact tenant/company scope.

Revision ID: 20260901_0055
Revises: 20260831_0054
"""

from alembic import op

revision = "20260901_0055"
down_revision = "20260831_0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION app.get_wecom_enterprise_authorization_for_scope(
          p_suite_id_hmac text,
          p_tenant_id uuid,
          p_company_id uuid
        )
        RETURNS TABLE (
          authorization_id uuid,
          auth_corpid_ciphertext bytea,
          permanent_code_ciphertext bytea,
          authorization_ciphertext bytea,
          authorizer_user_id_ciphertext bytea,
          encryption_key_ref text,
          agent_id integer
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
          SELECT authz.id,
                 authz.auth_corpid_ciphertext,
                 authz.permanent_code_ciphertext,
                 authz.authorization_ciphertext,
                 authz.authorizer_user_id_ciphertext,
                 authz.encryption_key_ref,
                 authz.agent_id
          FROM public.wecom_enterprise_scopes AS scope
          JOIN public.wecom_enterprise_authorizations AS authz
            ON authz.auth_corpid_hmac = scope.corp_id_hmac
           AND authz.suite_id_hmac = p_suite_id_hmac
          JOIN public.tenants AS tenant
            ON tenant.id = scope.tenant_id
          JOIN public.companies AS company
            ON company.id = scope.company_id
           AND company.tenant_id = scope.tenant_id
          WHERE length(p_suite_id_hmac) = 64
            AND scope.tenant_id = p_tenant_id
            AND scope.company_id = p_company_id
            AND authz.status = 'active'
            AND authz.revoked_at IS NULL
            AND tenant.status = 'active'
            AND tenant.deleted_at IS NULL
            AND company.status = 'active'
            AND company.deleted_at IS NULL
          LIMIT 1
        $$
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "app.get_wecom_enterprise_authorization_for_scope(text, uuid, uuid) "
        "FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT EXECUTE ON FUNCTION
              app.get_wecom_enterprise_authorization_for_scope(text, uuid, uuid)
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS app.get_wecom_enterprise_authorization_for_scope(text, uuid, uuid)"
    )
