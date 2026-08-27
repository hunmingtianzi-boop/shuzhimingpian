"""Grant the analysis worker read access to company LLM configuration.

Revision ID: 20260826_0050
Revises: 20260823_0049
"""

from alembic import op

revision = "20260826_0050"
down_revision = "20260823_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT SELECT ON company_llm_configurations TO cf_ai_card_worker;
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            REVOKE SELECT ON company_llm_configurations FROM cf_ai_card_worker;
          END IF;
        END
        $$;
        """
    )
