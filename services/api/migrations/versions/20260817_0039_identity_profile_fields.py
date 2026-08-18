"""Add employee public identity profile fields.

Revision ID: 20260817_0039
Revises: 20260814_0038
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0039"
down_revision: str | None = "20260814_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column("public_positioning", sa.String(length=240), nullable=True),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "identity_titles",
            postgresql.ARRAY(sa.String(length=80)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "professional_tags",
            postgresql.ARRAY(sa.String(length=40)),
            nullable=False,
            server_default=sa.text("'{}'::varchar[]"),
        ),
    )
    op.execute(
        """
        UPDATE memberships AS membership
        SET identity_titles = legacy.identity_titles
        FROM (
          SELECT DISTINCT ON (owner_user_id, tenant_id, company_id)
            owner_user_id,
            tenant_id,
            company_id,
            ARRAY(
              SELECT value
              FROM jsonb_array_elements_text(
                CASE
                  WHEN jsonb_typeof(settings->'identity_titles') = 'array'
                    THEN settings->'identity_titles'
                  ELSE '[]'::jsonb
                END
              ) AS value
              WHERE btrim(value) <> ''
              LIMIT 8
            )::varchar[] AS identity_titles
          FROM cards
          WHERE card_kind = 'employee'
            AND owner_user_id IS NOT NULL
            AND deleted_at IS NULL
          ORDER BY owner_user_id, tenant_id, company_id, updated_at DESC, id DESC
        ) AS legacy
        WHERE membership.user_id = legacy.owner_user_id
          AND membership.tenant_id = legacy.tenant_id
          AND membership.company_id = legacy.company_id
          AND cardinality(membership.identity_titles) = 0
        """
    )


def downgrade() -> None:
    op.drop_column("memberships", "professional_tags")
    op.drop_column("memberships", "identity_titles")
    op.drop_column("memberships", "public_positioning")
