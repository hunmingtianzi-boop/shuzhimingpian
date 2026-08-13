"""Add reviewable enterprise content classification candidates.

Revision ID: 20260812_0029
Revises: 20260807_0028
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260812_0029"
down_revision = "20260807_0028"
branch_labels = None
depends_on = None

RUN_COLUMNS = {
    "id", "tenant_id", "company_id", "batch_id", "requested_by", "status",
    "provider", "model", "attempts", "failure_code", "counts", "completed_at",
    "created_at", "updated_at",
}
CANDIDATE_COLUMNS = {
    "id", "tenant_id", "company_id", "run_id", "category", "payload",
    "source_id", "source_text", "confidence", "fingerprint", "status",
    "target_resource_type", "target_resource_id", "reviewed_by", "reviewed_at",
    "version", "created_at", "updated_at",
}


def _scope_table(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table_name}_scope_isolation ON {table_name} "
        "FOR ALL USING (app.scope_matches(tenant_id, company_id)) "
        "WITH CHECK (app.scope_matches(tenant_id, company_id))"
    )
    op.execute(f"REVOKE ALL ON TABLE {table_name} FROM PUBLIC")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table_name} TO cf_ai_card_app")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    existing = {"content_import_runs", "content_import_candidates"} & tables
    if existing:
        if existing != {"content_import_runs", "content_import_candidates"}:
            raise RuntimeError("content import review schema is only partially provisioned")
        run_columns = {column["name"] for column in inspector.get_columns("content_import_runs")}
        candidate_columns = {
            column["name"] for column in inspector.get_columns("content_import_candidates")
        }
        if not RUN_COLUMNS <= run_columns or not CANDIDATE_COLUMNS <= candidate_columns:
            raise RuntimeError("existing content import review schema is incompatible")
        return

    op.create_table(
        "content_import_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="processing"),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(500), nullable=True),
        sa.Column(
            "counts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "batch_id"],
            [
                "knowledge_import_batches.tenant_id",
                "knowledge_import_batches.company_id",
                "knowledge_import_batches.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_content_import_runs_scope_id"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "batch_id",
            name="uq_content_import_runs_scope_batch",
        ),
        sa.CheckConstraint(
            "status IN ('processing','review','manual_required')",
            name="content_import_run_status_allowed",
        ),
        sa.CheckConstraint("attempts >= 0 AND attempts <= 2", name="attempts_allowed"),
    )
    op.create_index(
        "ix_content_import_runs_company_created",
        "content_import_runs",
        ["company_id", "created_at"],
    )
    op.create_index(
        "ix_content_import_runs_batch_created",
        "content_import_runs",
        ["batch_id", "created_at"],
    )

    op.create_table(
        "content_import_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending_review"),
        sa.Column("target_resource_type", sa.String(40), nullable=True),
        sa.Column("target_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "run_id"],
            [
                "content_import_runs.tenant_id",
                "content_import_runs.company_id",
                "content_import_runs.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_content_import_candidates_scope_id"
        ),
        sa.UniqueConstraint("run_id", "fingerprint", name="uq_content_import_candidates_run_hash"),
        sa.CheckConstraint(
            "category IN ('enterprise_profile','products','case_studies','faqs','unclassified')",
            name="content_import_candidate_category_allowed",
        ),
        sa.CheckConstraint(
            "status IN ('pending_review','accepted','ignored','conflict')",
            name="content_import_candidate_status_allowed",
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.CheckConstraint("char_length(fingerprint) = 64", name="fingerprint_sha256"),
    )
    op.create_index(
        "ix_content_import_candidates_run_status",
        "content_import_candidates",
        ["run_id", "status", "created_at"],
    )
    op.create_index(
        "ix_content_import_candidates_company_category",
        "content_import_candidates",
        ["company_id", "category", "status"],
    )

    for table_name in ("content_import_runs", "content_import_candidates"):
        op.execute(
            f"CREATE TRIGGER trg_{table_name}_touch_updated_at BEFORE UPDATE ON {table_name} "
            "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
        )
        _scope_table(table_name)


def downgrade() -> None:
    op.drop_table("content_import_candidates")
    op.drop_table("content_import_runs")
