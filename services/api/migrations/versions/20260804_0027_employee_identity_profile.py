"""Make company membership the employee-card identity source.

Revision ID: 20260804_0027
Revises: 20260801_0026
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260804_0027"
down_revision: str | None = "20260801_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column("job_title", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "memberships",
        sa.Column("avatar_url", sa.String(length=2_048), nullable=True),
    )
    op.add_column(
        "memberships",
        sa.Column("business_summary", sa.Text(), nullable=True),
    )

    # A member can have several historic cards. The newest non-deleted employee
    # card is the deterministic compatibility source for the one-time backfill.
    op.execute(
        """
        WITH ranked_employee_cards AS (
            SELECT
                card.tenant_id,
                card.company_id,
                card.owner_user_id,
                NULLIF(btrim(card.settings ->> 'title'), '') AS job_title,
                NULLIF(btrim(card.settings ->> 'avatar_url'), '') AS avatar_url,
                NULLIF(btrim(card.settings ->> 'business_summary'), '') AS business_summary,
                row_number() OVER (
                    PARTITION BY card.tenant_id, card.company_id, card.owner_user_id
                    ORDER BY card.updated_at DESC, card.id DESC
                ) AS rank
            FROM cards AS card
            WHERE card.card_kind = 'employee'
              AND card.owner_user_id IS NOT NULL
              AND card.deleted_at IS NULL
        )
        UPDATE memberships AS membership
        SET
            job_title = ranked.job_title,
            avatar_url = ranked.avatar_url,
            business_summary = ranked.business_summary
        FROM ranked_employee_cards AS ranked
        WHERE ranked.rank = 1
          AND membership.tenant_id = ranked.tenant_id
          AND membership.company_id = ranked.company_id
          AND membership.user_id = ranked.owner_user_id
        """
    )
    op.execute(
        """
        UPDATE cards AS card
        SET
            display_name = app_user.display_name,
            settings = card.settings - 'title' - 'avatar_url' - 'business_summary'
        FROM users AS app_user
        WHERE card.card_kind = 'employee'
          AND card.owner_user_id = app_user.id
        """
    )
    # Give every historic enterprise card a schema-valid compatibility draft.
    # Already-published cards receive the same immutable public snapshot so the
    # new renderer never needs to read a mutable draft.
    op.execute(
        """
        UPDATE cards AS card
        SET settings = card.settings
            || jsonb_build_object(
                'enterprise_template_draft',
                jsonb_build_object(
                    'schema_version', 1,
                    'theme_key', 'brand',
                    'blocks', jsonb_build_array(
                        jsonb_build_object(
                            'id', 'legacy-intro',
                            'type', 'rich_text',
                            'visible', true,
                            'sort_order', 0,
                            'title', '企业介绍',
                            'body', COALESCE(
                                NULLIF(card.settings ->> 'title', ''),
                                card.display_name
                            ),
                            'image_urls', '[]'::jsonb,
                            'case_ids', '[]'::jsonb,
                            'case_items', '[]'::jsonb
                        )
                    )
                )
            )
            || CASE
                WHEN card.status = 'published' THEN jsonb_build_object(
                    'enterprise_template_published',
                    jsonb_build_object(
                        'schema_version', 1,
                        'theme_key', 'brand',
                        'blocks', jsonb_build_array(
                            jsonb_build_object(
                                'id', 'legacy-intro',
                                'type', 'rich_text',
                                'visible', true,
                                'sort_order', 0,
                                'title', '企业介绍',
                                'body', COALESCE(
                                    NULLIF(card.settings ->> 'title', ''),
                                    card.display_name
                                ),
                                'image_urls', '[]'::jsonb,
                                'case_ids', '[]'::jsonb,
                                'case_items', '[]'::jsonb
                            )
                        )
                    )
                )
                ELSE '{}'::jsonb
               END
        WHERE card.card_kind = 'enterprise'
          AND NOT (card.settings ? 'enterprise_template_draft')
        """
    )


def downgrade() -> None:
    # Restore the legacy card identity keys before removing the canonical member
    # profile columns so a code rollback keeps employee cards renderable.
    op.execute(
        """
        UPDATE cards AS card
        SET settings = card.settings
            || jsonb_build_object(
                'title', COALESCE(NULLIF(membership.job_title, ''), card.display_name)
            )
            || CASE
                WHEN membership.avatar_url IS NULL THEN '{}'::jsonb
                ELSE jsonb_build_object('avatar_url', membership.avatar_url)
               END
            || CASE
                WHEN membership.business_summary IS NULL THEN '{}'::jsonb
                ELSE jsonb_build_object('business_summary', membership.business_summary)
               END
        FROM memberships AS membership
        WHERE card.card_kind = 'employee'
          AND card.tenant_id = membership.tenant_id
          AND card.company_id = membership.company_id
          AND card.owner_user_id = membership.user_id
        """
    )
    op.execute(
        """
        UPDATE cards
        SET settings = settings
            - 'enterprise_template_draft'
            - 'enterprise_template_published'
        WHERE card_kind = 'enterprise'
        """
    )
    op.drop_column("memberships", "business_summary")
    op.drop_column("memberships", "avatar_url")
    op.drop_column("memberships", "job_title")
