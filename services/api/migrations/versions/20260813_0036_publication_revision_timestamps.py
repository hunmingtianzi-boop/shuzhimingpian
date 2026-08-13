"""Provide database timestamps for publication revision rows.

Revision ID: 20260813_0036
Revises: 20260813_0035
"""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0036"
down_revision = "20260813_0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "content_publication_revisions",
        "created_at",
        server_default=sa.func.now(),
    )
    op.alter_column(
        "content_publication_revisions",
        "updated_at",
        server_default=sa.func.now(),
    )


def downgrade() -> None:
    op.alter_column(
        "content_publication_revisions",
        "updated_at",
        server_default=None,
    )
    op.alter_column(
        "content_publication_revisions",
        "created_at",
        server_default=None,
    )
