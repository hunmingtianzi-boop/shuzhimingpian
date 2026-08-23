from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = (
    ROOT
    / (
        "services/api/migrations/versions/"
        "20260823_0046_platform_enterprise_identity_and_cardless_onboarding.py"
    )
)


def test_platform_identity_migration_adds_service_valid_until_column() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert '"service_valid_until"' in sql
    assert "DateTime(timezone=True)" in sql


def test_platform_identity_migration_guards_not_null_rollback_for_cardless_rows() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "initial_card_id IS NULL" in sql
    assert "cannot downgrade 20260823_0046 while cardless onboarding rows exist" in sql
