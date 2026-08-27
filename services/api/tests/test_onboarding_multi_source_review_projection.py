from pathlib import Path


def test_projection_aggregates_latest_run_for_every_attached_batch() -> None:
    migration = Path(
        "services/api/migrations/versions/20260826_0051_onboarding_multi_source_review_projection.py"
    ).read_text(encoding="utf-8")

    assert "PARTITION BY onboarding.id, bound_batch.batch_id" in migration
    assert "candidate.run_id = ANY(summary.run_ids)" in migration
    assert "GREATEST(pg_catalog.sum(progress_total)::integer, 1)" in migration
    assert "pg_catalog.max(started_at) AS started_at" in migration
    assert "正在分析 %s/%s 份资料" in migration
    assert "已完成 %s 份资料分析，共生成 %s 条候选" in migration
