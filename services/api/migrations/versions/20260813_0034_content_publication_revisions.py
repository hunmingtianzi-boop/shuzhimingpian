"""Add versioned publication snapshots for catalog content.

Revision ID: 20260813_0034
Revises: 20260813_0033
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260813_0034"
down_revision = "20260813_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_publication_revisions",
        sa.Column("resource_type", sa.String(32), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "revision_number >= 1",
            name="ck_content_publication_revisions_revision_number_positive",
        ),
        sa.CheckConstraint(
            "resource_type IN ('product', 'case_study')",
            name="ck_content_publication_revisions_resource_type_supported",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "resource_type",
            "resource_id",
            "revision_number",
            name="uq_content_publication_revision_number",
        ),
    )
    op.create_index(
        "ix_content_publication_revisions_resource",
        "content_publication_revisions",
        ["company_id", "resource_type", "resource_id", "revision_number"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_content_publication_revisions_resource",
        table_name="content_publication_revisions",
    )
    op.drop_table("content_publication_revisions")
