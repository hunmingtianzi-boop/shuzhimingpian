"""Add the enterprise monthly AI quota lookup index.

Revision ID: 20260828_0053
Revises: 20260826_0052
"""

import sqlalchemy as sa
from alembic import op

revision = "20260828_0053"
down_revision = "20260826_0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_messages_company_ai_quota",
        "messages",
        ["company_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("role = 'assistant' AND status <> 'failed'"),
    )


def downgrade() -> None:
    op.drop_index("ix_messages_company_ai_quota", table_name="messages")
