"""Bridge the restored local revision marker into the canonical chain.

Revision ID: 20260716_0026
Revises: 20260807_0028

Some restored development databases were stamped with this historical marker
from the same pre-content-review schema state as 0028. Keeping it as an
explicit no-op branch lets Alembic reconcile those databases without an unsafe
manual stamp; the following merge revision still applies the real 0029 DDL.
"""

revision = "20260716_0026"
down_revision = "20260807_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
