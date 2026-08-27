"""Persist cross-source onboarding synthesis lifecycle.

Revision ID: 20260826_0052
Revises: 20260826_0051
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_0052"
down_revision = "20260826_0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column(
            "synthesis_status",
            sa.String(length=24),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column("synthesis_failure_code", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column("synthesis_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column("synthesis_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_onboarding_sessions",
        sa.Column("synthesis_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "synthesis_status_allowed",
        "platform_onboarding_sessions",
        "synthesis_status IN ('pending','processing','ready','failed')",
    )
    op.create_check_constraint(
        "synthesis_version_non_negative",
        "platform_onboarding_sessions",
        "synthesis_version >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "synthesis_version_non_negative", "platform_onboarding_sessions", type_="check"
    )
    op.drop_constraint(
        "synthesis_status_allowed", "platform_onboarding_sessions", type_="check"
    )
    op.drop_column("platform_onboarding_sessions", "synthesis_version")
    op.drop_column("platform_onboarding_sessions", "synthesis_completed_at")
    op.drop_column("platform_onboarding_sessions", "synthesis_started_at")
    op.drop_column("platform_onboarding_sessions", "synthesis_failure_code")
    op.drop_column("platform_onboarding_sessions", "synthesis_status")
