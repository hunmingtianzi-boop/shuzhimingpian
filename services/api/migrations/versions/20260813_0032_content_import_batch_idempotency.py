"""Enforce one authoritative classification run per import batch.

Revision ID: 20260813_0032
Revises: 20260813_0031
"""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0032"
down_revision = "20260813_0031"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "uq_content_import_runs_scope_batch"


def _constraint_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        constraint.get("name") == CONSTRAINT_NAME
        for constraint in inspector.get_unique_constraints("content_import_runs")
    )


def upgrade() -> None:
    if not _constraint_exists():
        op.create_unique_constraint(
            CONSTRAINT_NAME,
            "content_import_runs",
            ["tenant_id", "company_id", "batch_id"],
        )


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(CONSTRAINT_NAME, "content_import_runs", type_="unique")
