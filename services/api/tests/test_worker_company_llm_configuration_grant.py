from pathlib import Path


def test_analysis_worker_can_read_company_llm_configuration() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations/versions/20260826_0050_worker_company_llm_configuration_grant.py"
    ).read_text(encoding="utf-8").casefold()

    assert "grant select on company_llm_configurations to cf_ai_card_worker" in migration
    assert "revoke select on company_llm_configurations from cf_ai_card_worker" in migration
    assert 'down_revision = "20260823_0049"' in migration
