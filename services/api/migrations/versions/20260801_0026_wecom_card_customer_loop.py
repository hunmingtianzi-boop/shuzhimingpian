"""Connect employee cards to attributed WeCom customer contacts.

Revision ID: 20260801_0026
Revises: 20260730_0025
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260801_0026"
down_revision = "20260730_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wecom_card_contact_ways",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_token_hmac", sa.String(length=64), nullable=False),
        sa.Column("config_id_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("config_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("qr_code_url_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("encryption_key_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "provisioned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "char_length(state_token_hmac) = 64",
            name="wecom_card_contact_state_hmac_sha256",
        ),
        sa.CheckConstraint(
            "char_length(config_id_hmac) = 64",
            name="wecom_card_contact_config_hmac_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["wecom_user_bindings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "state_token_hmac",
            name="uq_wecom_card_contact_ways_state",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "config_id_hmac",
            name="uq_wecom_card_contact_ways_config",
        ),
    )
    op.create_index(
        "uq_wecom_card_contact_ways_active_card",
        "wecom_card_contact_ways",
        ["tenant_id", "company_id", "card_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_wecom_card_contact_ways_owner_active",
        "wecom_card_contact_ways",
        ["owner_user_id", "revoked_at", "updated_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_wecom_card_contact_ways_touch_updated_at "
        "BEFORE UPDATE ON wecom_card_contact_ways "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    op.create_table(
        "wecom_customer_links",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contact_way_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_user_id_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("external_user_id_hmac", sa.String(length=64), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("encryption_key_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "added_at",
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
        sa.CheckConstraint(
            "char_length(external_user_id_hmac) = 64",
            name="wecom_customer_external_hmac_sha256",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id", "lead_id"],
            ["leads.tenant_id", "leads.company_id", "leads.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_way_id"], ["wecom_card_contact_ways.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"], ["wecom_user_bindings.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id",
            "company_id",
            "binding_id",
            "external_user_id_hmac",
            name="uq_wecom_customer_links_owner_external",
        ),
    )
    op.create_index(
        "ix_wecom_customer_links_card_created",
        "wecom_customer_links",
        ["card_id", "created_at"],
    )
    op.execute(
        "CREATE TRIGGER trg_wecom_customer_links_touch_updated_at "
        "BEFORE UPDATE ON wecom_customer_links "
        "FOR EACH ROW EXECUTE FUNCTION app.touch_updated_at()"
    )

    for table_name in ("wecom_card_contact_ways", "wecom_customer_links"):
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
              wecom_card_contact_ways, wecom_customer_links
              TO cf_ai_card_app;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_worker') THEN
            GRANT SELECT ON wecom_user_bindings TO cf_ai_card_worker;
          END IF;
        END $grant$
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS wecom_customer_links_scope_isolation ON wecom_customer_links"
    )
    op.execute(
        "DROP POLICY IF EXISTS wecom_card_contact_ways_scope_isolation "
        "ON wecom_card_contact_ways"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_wecom_customer_links_touch_updated_at "
        "ON wecom_customer_links"
    )
    op.drop_index(
        "ix_wecom_customer_links_card_created", table_name="wecom_customer_links"
    )
    op.drop_table("wecom_customer_links")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_wecom_card_contact_ways_touch_updated_at "
        "ON wecom_card_contact_ways"
    )
    op.drop_index(
        "ix_wecom_card_contact_ways_owner_active",
        table_name="wecom_card_contact_ways",
    )
    op.drop_index(
        "uq_wecom_card_contact_ways_active_card",
        table_name="wecom_card_contact_ways",
    )
    op.drop_table("wecom_card_contact_ways")
