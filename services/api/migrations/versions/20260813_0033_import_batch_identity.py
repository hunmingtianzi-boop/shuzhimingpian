"""Add human-readable import batch identity.

Revision ID: 20260813_0033
Revises: 20260813_0032
"""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0033"
down_revision = "20260813_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_import_batches", sa.Column("sequence_number", sa.Integer()))
    op.add_column("knowledge_import_batches", sa.Column("display_name", sa.String(120)))
    op.add_column(
        "knowledge_import_batches",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.execute(
        """
        WITH numbered AS (
          SELECT id,
                 row_number() OVER (
                   PARTITION BY tenant_id, company_id ORDER BY created_at, id
                 ) AS seq
          FROM knowledge_import_batches
        )
        UPDATE knowledge_import_batches AS batch
        SET sequence_number = numbered.seq,
            display_name = '资料导入 #' || lpad(numbered.seq::text, 3, '0')
        FROM numbered
        WHERE batch.id = numbered.id
        """
    )
    op.alter_column("knowledge_import_batches", "sequence_number", nullable=False)
    op.alter_column("knowledge_import_batches", "display_name", nullable=False)
    op.create_unique_constraint(
        "uq_knowledge_import_batches_company_sequence",
        "knowledge_import_batches",
        ["tenant_id", "company_id", "sequence_number"],
    )
    op.create_check_constraint(
        "ck_knowledge_import_batches_sequence_number_positive",
        "knowledge_import_batches",
        "sequence_number > 0",
    )
    op.create_check_constraint(
        "ck_knowledge_import_batches_display_name_non_empty",
        "knowledge_import_batches",
        "char_length(btrim(display_name)) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_knowledge_import_batches_display_name_non_empty",
        "knowledge_import_batches",
        type_="check",
    )
    op.drop_constraint(
        "ck_knowledge_import_batches_sequence_number_positive",
        "knowledge_import_batches",
        type_="check",
    )
    op.drop_constraint(
        "uq_knowledge_import_batches_company_sequence",
        "knowledge_import_batches",
        type_="unique",
    )
    op.drop_column("knowledge_import_batches", "version")
    op.drop_column("knowledge_import_batches", "display_name")
    op.drop_column("knowledge_import_batches", "sequence_number")
