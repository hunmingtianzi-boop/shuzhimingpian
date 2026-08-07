"""Store encrypted third-party WeCom enterprise authorizations.

Revision ID: 20260807_0028
Revises: 20260807_0027, 20260804_0027
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260807_0028"
down_revision = ("20260807_0027", "20260804_0027")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wecom_enterprise_authorizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("suite_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("auth_corpid_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("auth_corpid_hmac", sa.String(length=64), nullable=False),
        sa.Column("permanent_code_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("authorization_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("authorizer_user_id_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("encryption_key_ref", sa.String(length=128), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column(
            "authorized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            "char_length(suite_id_hmac) = 64",
            name="suite_id_hmac_sha256",
        ),
        sa.CheckConstraint(
            "char_length(auth_corpid_hmac) = 64",
            name="auth_corpid_hmac_sha256",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="authorization_status_allowed",
        ),
        sa.UniqueConstraint(
            "suite_id_hmac",
            "auth_corpid_hmac",
            name="uq_wecom_enterprise_authorizations_provider_corp",
        ),
    )
    op.create_index(
        "ix_wecom_enterprise_authorizations_status",
        "wecom_enterprise_authorizations",
        ["suite_id_hmac", "status", "updated_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_wecom_enterprise_authorizations_touch_updated_at "
        "BEFORE UPDATE ON wecom_enterprise_authorizations "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )
    op.execute("REVOKE ALL ON TABLE wecom_enterprise_authorizations FROM PUBLIC")

    op.execute(
        r"""
        CREATE FUNCTION app.upsert_wecom_enterprise_authorization(
          p_suite_id_hmac text,
          p_auth_corpid_hmac text,
          p_auth_corpid_ciphertext bytea,
          p_permanent_code_ciphertext bytea,
          p_authorization_ciphertext bytea,
          p_authorizer_user_id_ciphertext bytea,
          p_encryption_key_ref text,
          p_agent_id integer
        )
        RETURNS uuid
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        DECLARE
          v_id uuid;
        BEGIN
          IF length(p_suite_id_hmac) <> 64
             OR length(p_auth_corpid_hmac) <> 64
             OR p_auth_corpid_ciphertext IS NULL
             OR p_permanent_code_ciphertext IS NULL
             OR p_authorization_ciphertext IS NULL
             OR length(btrim(p_encryption_key_ref)) NOT BETWEEN 1 AND 128
          THEN
            RAISE EXCEPTION 'invalid WeCom authorization input'
              USING ERRCODE = '22023';
          END IF;

          PERFORM pg_advisory_xact_lock(
            hashtextextended(
              'wecom-authorization:' || p_suite_id_hmac || ':' || p_auth_corpid_hmac,
              0
            )
          );

          INSERT INTO public.wecom_enterprise_authorizations (
            suite_id_hmac,
            auth_corpid_hmac,
            auth_corpid_ciphertext,
            permanent_code_ciphertext,
            authorization_ciphertext,
            authorizer_user_id_ciphertext,
            encryption_key_ref,
            agent_id,
            status,
            authorized_at,
            last_synced_at,
            revoked_at
          ) VALUES (
            p_suite_id_hmac,
            p_auth_corpid_hmac,
            p_auth_corpid_ciphertext,
            p_permanent_code_ciphertext,
            p_authorization_ciphertext,
            p_authorizer_user_id_ciphertext,
            p_encryption_key_ref,
            p_agent_id,
            'active',
            now(),
            now(),
            NULL
          )
          ON CONFLICT (suite_id_hmac, auth_corpid_hmac) DO UPDATE SET
            auth_corpid_ciphertext = EXCLUDED.auth_corpid_ciphertext,
            permanent_code_ciphertext = EXCLUDED.permanent_code_ciphertext,
            authorization_ciphertext = EXCLUDED.authorization_ciphertext,
            authorizer_user_id_ciphertext = EXCLUDED.authorizer_user_id_ciphertext,
            encryption_key_ref = EXCLUDED.encryption_key_ref,
            agent_id = EXCLUDED.agent_id,
            status = 'active',
            authorized_at = now(),
            last_synced_at = now(),
            revoked_at = NULL
          RETURNING id INTO v_id;

          RETURN v_id;
        END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.get_wecom_enterprise_authorization(
          p_suite_id_hmac text,
          p_auth_corpid_hmac text
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
          SELECT authorization.id,
                 authorization.auth_corpid_ciphertext,
                 authorization.permanent_code_ciphertext,
                 authorization.authorization_ciphertext,
                 authorization.authorizer_user_id_ciphertext,
                 authorization.encryption_key_ref,
                 authorization.agent_id
          FROM public.wecom_enterprise_authorizations AS authorization
          WHERE length(p_suite_id_hmac) = 64
            AND length(p_auth_corpid_hmac) = 64
            AND authorization.suite_id_hmac = p_suite_id_hmac
            AND authorization.auth_corpid_hmac = p_auth_corpid_hmac
            AND authorization.status = 'active'
            AND authorization.revoked_at IS NULL
          LIMIT 1
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.revoke_wecom_enterprise_authorization(
          p_suite_id_hmac text,
          p_auth_corpid_hmac text
        )
        RETURNS boolean
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
        BEGIN
          UPDATE public.wecom_enterprise_authorizations
          SET status = 'revoked', revoked_at = now(), last_synced_at = now()
          WHERE length(p_suite_id_hmac) = 64
            AND length(p_auth_corpid_hmac) = 64
            AND suite_id_hmac = p_suite_id_hmac
            AND auth_corpid_hmac = p_auth_corpid_hmac
            AND status <> 'revoked';
          RETURN FOUND;
        END
        $$
        """
    )
    op.execute(
        r"""
        CREATE FUNCTION app.resolve_wecom_enterprise_scope(p_corp_id_hmac text)
        RETURNS TABLE (tenant_id uuid, company_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, public, app
        AS $$
          SELECT scope.tenant_id, scope.company_id
          FROM public.wecom_enterprise_scopes AS scope
          JOIN public.tenants AS tenant ON tenant.id = scope.tenant_id
          JOIN public.companies AS company
            ON company.id = scope.company_id
           AND company.tenant_id = scope.tenant_id
          WHERE length(p_corp_id_hmac) = 64
            AND scope.corp_id_hmac = p_corp_id_hmac
            AND tenant.status = 'active'
            AND tenant.deleted_at IS NULL
            AND company.status = 'active'
            AND company.deleted_at IS NULL
          LIMIT 1
        $$
        """
    )

    signatures = (
        "app.upsert_wecom_enterprise_authorization("
        "text, text, bytea, bytea, bytea, bytea, text, integer)",
        "app.get_wecom_enterprise_authorization(text, text)",
        "app.revoke_wecom_enterprise_authorization(text, text)",
        "app.resolve_wecom_enterprise_scope(text)",
    )
    for signature in signatures:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT EXECUTE ON FUNCTION app.upsert_wecom_enterprise_authorization(
              text, text, bytea, bytea, bytea, bytea, text, integer
            ) TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.get_wecom_enterprise_authorization(text, text)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.revoke_wecom_enterprise_authorization(text, text)
              TO cf_ai_card_app;
            GRANT EXECUTE ON FUNCTION app.resolve_wecom_enterprise_scope(text)
              TO cf_ai_card_app;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.resolve_wecom_enterprise_scope(text)")
    op.execute(
        "DROP FUNCTION IF EXISTS app.revoke_wecom_enterprise_authorization(text, text)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app.get_wecom_enterprise_authorization(text, text)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS app.upsert_wecom_enterprise_authorization("
        "text, text, bytea, bytea, bytea, bytea, text, integer)"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_wecom_enterprise_authorizations_touch_updated_at "
        "ON wecom_enterprise_authorizations"
    )
    op.drop_index(
        "ix_wecom_enterprise_authorizations_status",
        table_name="wecom_enterprise_authorizations",
    )
    op.drop_table("wecom_enterprise_authorizations")
