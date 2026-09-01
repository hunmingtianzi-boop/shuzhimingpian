"""Backfill the business tenant key for legacy company creation paths.

Revision ID: 20260831_0054
Revises: 20260828_0053
"""

from alembic import op

revision = "20260831_0054"
down_revision = "20260828_0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE FUNCTION app.ensure_company_business_tenant_key()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public, app
        AS $$
        BEGIN
          IF NEW.business_tenant_key IS NULL
             OR btrim(NEW.business_tenant_key) = ''
          THEN
            NEW.business_tenant_key :=
              'org-' || substr(replace(NEW.id::text, '-', ''), 1, 24);
          END IF;
          RETURN NEW;
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_companies_ensure_business_tenant_key "
        "BEFORE INSERT ON companies "
        "FOR EACH ROW EXECUTE FUNCTION app.ensure_company_business_tenant_key()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_companies_ensure_business_tenant_key ON companies"
    )
    op.execute("DROP FUNCTION IF EXISTS app.ensure_company_business_tenant_key()")
