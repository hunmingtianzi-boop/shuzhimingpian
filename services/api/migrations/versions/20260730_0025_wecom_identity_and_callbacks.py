"""Add encrypted WeCom identity bindings and callback inbox.

Revision ID: 20260730_0025
Revises: 20260719_0024
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260730_0025"
down_revision = "20260719_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wecom_user_bindings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corp_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("wecom_user_id_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("wecom_user_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("profile_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("encryption_key_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(corp_id_hmac) = 64",
            name="corp_id_hmac_sha256",
        ),
        sa.CheckConstraint(
            "char_length(wecom_user_id_hmac) = 64",
            name="wecom_user_id_hmac_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["memberships.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "membership_id",
            name="uq_wecom_user_bindings_membership",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "corp_id_hmac",
            "wecom_user_id_hmac",
            name="uq_wecom_user_bindings_provider_user",
        ),
    )
    op.create_index(
        "ix_wecom_user_bindings_company_active",
        "wecom_user_bindings",
        ["company_id", "revoked_at", "updated_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_wecom_user_bindings_touch_updated_at "
        "BEFORE UPDATE ON wecom_user_bindings "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    op.create_table(
        "wecom_callback_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("corp_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("provider_event_key", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("change_type", sa.String(length=80), nullable=True),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'received'"),
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "char_length(corp_id_hmac) = 64",
            name="corp_id_hmac_sha256",
        ),
        sa.CheckConstraint(
            "char_length(provider_event_key) = 64",
            name="provider_event_key_sha256",
        ),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'failed')",
            name="status_allowed",
        ),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "provider_event_key",
            name="uq_wecom_callback_events_provider_key",
        ),
    )
    op.create_index(
        "ix_wecom_callback_events_processing",
        "wecom_callback_events",
        ["company_id", "status", "received_at"],
    )

    for table_name in ("wecom_user_bindings", "wecom_callback_events"):
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table_name}_scope_isolation ON {table_name} "
            "USING (app.scope_matches(tenant_id, company_id)) "
            "WITH CHECK (app.scope_matches(tenant_id, company_id))"
        )

    op.execute(
        """
        DO $grant$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
            GRANT SELECT, INSERT, UPDATE ON
              wecom_user_bindings, wecom_callback_events
              TO cf_ai_card_app;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS wecom_callback_events_scope_isolation "
        "ON wecom_callback_events"
    )
    op.execute("DROP POLICY IF EXISTS wecom_user_bindings_scope_isolation ON wecom_user_bindings")
    op.drop_index(
        "ix_wecom_callback_events_processing",
        table_name="wecom_callback_events",
    )
    op.drop_table("wecom_callback_events")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_wecom_user_bindings_touch_updated_at "
        "ON wecom_user_bindings"
    )
    op.drop_index(
        "ix_wecom_user_bindings_company_active",
        table_name="wecom_user_bindings",
    )
    op.drop_table("wecom_user_bindings")
