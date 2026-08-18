"""Grant the Worker access required by company visibility policies.

Revision ID: 20260818_0041
Revises: 20260818_0040
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260818_0041"
down_revision: str | None = "20260818_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles
            WHERE rolname = 'cf_ai_card_worker'
          ) THEN
            GRANT SELECT ON public.platform_onboarding_sessions
              TO cf_ai_card_worker;
          END IF;
        END
        $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $revoke$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_roles
            WHERE rolname = 'cf_ai_card_worker'
          ) THEN
            REVOKE SELECT ON public.platform_onboarding_sessions
              FROM cf_ai_card_worker;
          END IF;
        END
        $revoke$
        """
    )
