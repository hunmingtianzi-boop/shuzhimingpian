"""Allow workers to resolve suite authorization for the claimed company only.

Revision ID: 20260819_0043
Revises: 20260818_0042
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260819_0043"
down_revision: str | None = "20260818_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app.get_wecom_suite_authorization_for_scope(
          p_suite_id_hmac text,
          p_tenant_id uuid,
          p_company_id uuid
        ) RETURNS TABLE (
          auth_corpid_ciphertext bytea,
          permanent_code_ciphertext bytea,
          agent_id integer
        )
        LANGUAGE sql
        STABLE
        PARALLEL SAFE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
          SELECT
            authz.auth_corpid_ciphertext,
            authz.permanent_code_ciphertext,
            authz.agent_id
          FROM public.wecom_enterprise_scopes AS scope
          JOIN public.wecom_enterprise_authorizations AS authz
            ON authz.auth_corpid_hmac = scope.corp_id_hmac
          JOIN public.tenants AS tenant
            ON tenant.id = scope.tenant_id
          JOIN public.companies AS company
            ON company.id = scope.company_id
           AND company.tenant_id = scope.tenant_id
          WHERE length(p_suite_id_hmac) = 64
            AND scope.tenant_id = p_tenant_id
            AND scope.company_id = p_company_id
            AND authz.suite_id_hmac = p_suite_id_hmac
            AND authz.status = 'active'
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
        "app.get_wecom_suite_authorization_for_scope(text, uuid, uuid) FROM PUBLIC"
    )
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT EXECUTE ON FUNCTION
              app.get_wecom_suite_authorization_for_scope(text, uuid, uuid)
              TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS app.get_wecom_suite_authorization_for_scope(text, uuid, uuid)"
    )
