from pathlib import Path


def test_synthesis_lifecycle_is_persisted_and_guarded() -> None:
    migration = Path(
        "services/api/migrations/versions/20260826_0052_onboarding_cross_source_synthesis.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260826_0051"' in migration
    assert '"synthesis_status"' in migration
    assert "pending','processing','ready','failed" in migration
    assert '"synthesis_version"' in migration
    assert "synthesis_version >= 0" in migration
