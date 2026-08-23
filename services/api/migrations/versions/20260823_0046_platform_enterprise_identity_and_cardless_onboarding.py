"""Add platform enterprise identity fields and cardless onboarding support.

Revision ID: 20260823_0046
Revises: 20260819_0045
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260823_0046"
down_revision: str | None = "20260819_0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("short_name", sa.String(length=120), nullable=True))
    op.add_column(
        "companies",
        sa.Column(
            "subject_type",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'domestic_enterprise'"),
        ),
    )
    op.add_column(
        "companies",
        sa.Column("social_credit_code", sa.String(length=18), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("business_tenant_key", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("service_valid_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_companies_business_tenant_key",
        "companies",
        ["business_tenant_key"],
    )
    op.create_index(
        "uq_companies_social_credit_code",
        "companies",
        ["social_credit_code"],
        unique=True,
        postgresql_where=sa.text("social_credit_code IS NOT NULL"),
    )
    op.create_check_constraint(
        "companies_subject_type_allowed",
        "companies",
        "subject_type IN ('domestic_enterprise','association','overseas','pending_registration')",
    )
    op.execute(
        """
        UPDATE companies AS company
        SET business_tenant_key = CASE
          WHEN company.business_tenant_key IS NOT NULL THEN company.business_tenant_key
          WHEN tenant.slug ~ '^[A-Za-z0-9]{18}$' THEN upper(tenant.slug)
          ELSE 'org-' || substr(replace(company.id::text, '-', ''), 1, 24)
        END
        FROM tenants AS tenant
        WHERE tenant.id = company.tenant_id
        """
    )
    op.alter_column("companies", "business_tenant_key", nullable=False)
    op.alter_column("platform_onboarding_sessions", "initial_card_id", nullable=True)


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM platform_onboarding_sessions
            WHERE initial_card_id IS NULL
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade 20260823_0046 while cardless onboarding rows exist';
          END IF;
        END
        $$;
        """
    )
    op.alter_column("platform_onboarding_sessions", "initial_card_id", nullable=False)
    op.drop_constraint("companies_subject_type_allowed", "companies", type_="check")
    op.drop_index("uq_companies_social_credit_code", table_name="companies")
    op.drop_constraint("uq_companies_business_tenant_key", "companies", type_="unique")
    op.drop_column("companies", "service_valid_until")
    op.drop_column("companies", "business_tenant_key")
    op.drop_column("companies", "social_credit_code")
    op.drop_column("companies", "subject_type")
    op.drop_column("companies", "short_name")
