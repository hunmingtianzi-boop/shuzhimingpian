"""Secure publication revision storage for the application role.

Revision ID: 20260813_0035
Revises: 20260813_0034
"""

from alembic import op

revision = "20260813_0035"
down_revision = "20260813_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE content_publication_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE content_publication_revisions FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY content_publication_revisions_scope_isolation "
        "ON content_publication_revisions FOR ALL "
        "USING (app.scope_matches(tenant_id, company_id)) "
        "WITH CHECK (app.scope_matches(tenant_id, company_id))"
    )
    op.execute("REVOKE ALL ON TABLE content_publication_revisions FROM PUBLIC")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE "
        "ON TABLE content_publication_revisions TO cf_ai_card_app"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE "
        "ON TABLE content_publication_revisions FROM cf_ai_card_app"
    )
    op.execute(
        "DROP POLICY IF EXISTS content_publication_revisions_scope_isolation "
        "ON content_publication_revisions"
    )
    op.execute("ALTER TABLE content_publication_revisions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE content_publication_revisions DISABLE ROW LEVEL SECURITY")
