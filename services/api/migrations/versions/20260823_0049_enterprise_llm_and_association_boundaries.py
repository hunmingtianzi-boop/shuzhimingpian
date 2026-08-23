"""Add enterprise LLM access and association membership boundaries.

Revision ID: 20260823_0049
Revises: 20260823_0048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0049"
down_revision: str | None = "20260823_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The platform API has supported up to 65,536 output tokens since the
    # multi-profile control plane was introduced, while the original database
    # constraint still capped rows at 8,192. Align the persistence boundary so
    # the UI's valid defaults cannot fail as a generic write conflict.
    op.drop_constraint(
        "max_output_tokens_range",
        "platform_llm_profiles",
        type_="check",
    )
    op.create_check_constraint(
        "max_output_tokens_range",
        "platform_llm_profiles",
        "max_output_tokens >= 128 AND max_output_tokens <= 65536",
    )

    op.create_table(
        "company_llm_configurations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "mode", sa.String(24), nullable=False, server_default=sa.text("'platform_managed'")
        ),
        sa.Column("api_key_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("api_key_key_ref", sa.String(128), nullable=True),
        sa.Column("api_key_hint", sa.String(32), nullable=True),
        sa.Column(
            "daily_budget_cny", sa.Numeric(12, 2), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delegated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("delegated_reason", sa.String(500), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id", "company_id"], ["companies.tenant_id", "companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["platform_profile_id"], ["platform_llm_profiles.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("tenant_id", "company_id", name="uq_company_llm_configurations_scope"),
        sa.CheckConstraint("mode IN ('platform_managed', 'byok')", name="mode_allowed"),
        sa.CheckConstraint("daily_budget_cny >= 0", name="daily_budget_non_negative"),
        sa.CheckConstraint(
            "(mode = 'platform_managed' AND api_key_ciphertext IS NULL "
            "AND api_key_key_ref IS NULL AND api_key_hint IS NULL) OR "
            "(mode = 'byok' AND api_key_ciphertext IS NOT NULL "
            "AND api_key_key_ref IS NOT NULL AND api_key_hint IS NOT NULL)",
            name="credential_state",
        ),
        sa.CheckConstraint("version > 0", name="version_positive"),
    )
    op.create_index(
        "ix_company_llm_configurations_profile",
        "company_llm_configurations",
        ["platform_profile_id"],
    )
    op.execute(
        "CREATE TRIGGER trg_company_llm_configurations_touch_updated_at "
        "BEFORE UPDATE ON company_llm_configurations FOR EACH ROW "
        "EXECUTE FUNCTION app.touch_updated_at()"
    )
    op.execute("ALTER TABLE company_llm_configurations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_llm_configurations_scope_select "
        "ON company_llm_configurations FOR SELECT USING "
        "(app.scope_matches(tenant_id, company_id) OR app.platform_actor_allowed())"
    )
    op.execute(
        "CREATE POLICY company_llm_configurations_scope_insert "
        "ON company_llm_configurations FOR INSERT WITH CHECK "
        "(app.scope_matches(tenant_id, company_id) OR app.platform_actor_allowed())"
    )
    op.execute(
        "CREATE POLICY company_llm_configurations_scope_update "
        "ON company_llm_configurations FOR UPDATE USING "
        "(app.scope_matches(tenant_id, company_id) OR app.platform_actor_allowed()) "
        "WITH CHECK "
        "(app.scope_matches(tenant_id, company_id) OR app.platform_actor_allowed())"
    )

    op.create_table(
        "association_company_memberships",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("association_tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("association_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("member_tier", sa.String(80), nullable=True),
        sa.Column("allocated_seats", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "benefits", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["association_tenant_id", "association_company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["member_tenant_id", "member_company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "association_company_id",
            "member_company_id",
            name="uq_association_company_memberships_pair",
        ),
        sa.CheckConstraint(
            "association_company_id <> member_company_id", name="association_member_distinct"
        ),
        sa.CheckConstraint("allocated_seats >= 0", name="allocated_seats_non_negative"),
        sa.CheckConstraint("version > 0", name="version_positive"),
    )
    op.create_index(
        "ix_association_memberships_association",
        "association_company_memberships",
        ["association_company_id"],
    )
    op.create_index(
        "ix_association_memberships_member",
        "association_company_memberships",
        ["member_company_id"],
    )
    op.execute(
        "CREATE TRIGGER trg_association_company_memberships_touch_updated_at "
        "BEFORE UPDATE ON association_company_memberships FOR EACH ROW "
        "EXECUTE FUNCTION app.touch_updated_at()"
    )
    op.execute("ALTER TABLE association_company_memberships ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY association_company_memberships_platform_all "
        "ON association_company_memberships FOR ALL "
        "USING (app.platform_actor_allowed()) WITH CHECK (app.platform_actor_allowed())"
    )

    op.execute(
        "REVOKE ALL ON TABLE company_llm_configurations, "
        "association_company_memberships FROM PUBLIC"
    )
    op.execute("""
    DO $grant$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cf_ai_card_app') THEN
        GRANT SELECT, INSERT, UPDATE ON company_llm_configurations TO cf_ai_card_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON association_company_memberships TO cf_ai_card_app;
      END IF;
    END $grant$
    """)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS association_company_memberships_platform_all "
        "ON association_company_memberships"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_association_company_memberships_touch_updated_at "
        "ON association_company_memberships"
    )
    op.drop_table("association_company_memberships")
    config_count = op.get_bind().scalar(sa.text("SELECT count(*) FROM company_llm_configurations"))
    if int(config_count or 0) > 0:
        raise RuntimeError(
            "refusing to drop company_llm_configurations while encrypted settings exist"
        )
    op.execute(
        "DROP POLICY IF EXISTS company_llm_configurations_scope_update "
        "ON company_llm_configurations"
    )
    op.execute(
        "DROP POLICY IF EXISTS company_llm_configurations_scope_insert "
        "ON company_llm_configurations"
    )
    op.execute(
        "DROP POLICY IF EXISTS company_llm_configurations_scope_select "
        "ON company_llm_configurations"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_company_llm_configurations_touch_updated_at "
        "ON company_llm_configurations"
    )
    op.drop_table("company_llm_configurations")
    op.drop_constraint(
        "max_output_tokens_range",
        "platform_llm_profiles",
        type_="check",
    )
    op.create_check_constraint(
        "max_output_tokens_range",
        "platform_llm_profiles",
        "max_output_tokens >= 128 AND max_output_tokens <= 8192",
    )
