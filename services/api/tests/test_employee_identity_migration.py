from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

API_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    API_ROOT
    / "migrations"
    / "versions"
    / "20260804_0027_employee_identity_profile.py"
)


class _MigrationOperations:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, object | None]] = []

    def add_column(self, table_name: str, column: object) -> None:
        self.events.append(("add_column", table_name, column))

    def execute(self, statement: str) -> None:
        self.events.append(("execute", statement, None))

    def drop_column(self, table_name: str, column_name: str) -> None:
        self.events.append(("drop_column", table_name, column_name))


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("employee_identity_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalized_sql(events: list[tuple[str, str, object | None]]) -> str:
    return " ".join(
        " ".join(value.split())
        for kind, value, _ in events
        if kind == "execute"
    ).casefold()


def test_upgrade_backfills_latest_employee_card_then_removes_identity_copies() -> None:
    migration = _load_migration()
    operations = _MigrationOperations()
    migration.op = operations

    migration.upgrade()

    added_columns = [
        cast_column.name
        for event, table, cast_column in operations.events
        if event == "add_column" and table == "memberships"
    ]
    assert added_columns == ["job_title", "avatar_url", "business_summary"]
    sql = _normalized_sql(operations.events)
    assert "row_number() over" in sql
    assert "partition by card.tenant_id, card.company_id, card.owner_user_id" in sql
    assert "order by card.updated_at desc, card.id desc" in sql
    assert "update memberships as membership" in sql
    assert "display_name = app_user.display_name" in sql
    assert "settings = card.settings - 'title' - 'avatar_url' - 'business_summary'" in sql
    assert "enterprise_template_draft" in sql
    assert "enterprise_template_published" in sql
    assert "legacy-intro" in sql


def test_downgrade_restores_legacy_card_identity_before_dropping_profile_columns() -> None:
    migration = _load_migration()
    operations = _MigrationOperations()
    migration.op = operations

    migration.downgrade()

    assert operations.events[0][0] == "execute"
    sql = _normalized_sql(operations.events)
    assert "jsonb_build_object" in sql
    assert "membership.job_title" in sql
    assert "membership.avatar_url" in sql
    assert "membership.business_summary" in sql
    assert "- 'enterprise_template_draft'" in sql
    dropped = [
        column_name
        for event, table, column_name in operations.events
        if event == "drop_column" and table == "memberships"
    ]
    assert dropped == ["business_summary", "avatar_url", "job_title"]


def test_migration_extends_the_current_single_head() -> None:
    migration = _load_migration()

    assert migration.revision == "20260804_0027"
    assert migration.down_revision == "20260801_0026"
