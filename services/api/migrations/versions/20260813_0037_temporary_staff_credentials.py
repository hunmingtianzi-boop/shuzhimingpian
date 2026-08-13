"""Add one-time temporary credential state.

Revision ID: 20260813_0037
Revises: 20260813_0036
"""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0037"
down_revision = "20260813_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff_credentials",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "staff_credentials",
        sa.Column("temporary_password_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("staff_credentials", "temporary_password_expires_at")
    op.drop_column("staff_credentials", "must_change_password")
