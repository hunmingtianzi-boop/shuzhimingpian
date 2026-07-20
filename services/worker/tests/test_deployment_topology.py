from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_worker_and_beat_are_separate_processes_without_dbm_schedule() -> None:
    compose = yaml.safe_load((ROOT / "infra/compose.yaml").read_text())
    services = compose["services"]

    worker_command = (ROOT / "services/worker/Dockerfile").read_text()
    beat_command = services["beat"]["command"]

    assert '"worker", "--loglevel=INFO"' in worker_command
    assert '"worker", "--beat"' not in worker_command
    assert beat_command[:4] == [
        "celery",
        "-A",
        "cf_worker.celery_app:celery_app",
        "beat",
    ]
    assert "--scheduler=celery.beat:Scheduler" in beat_command
    assert all("schedule=" not in item for item in beat_command)
    assert services["worker"]["image"] == services["beat"]["image"]


def test_api_waits_for_atomic_knowledge_vector_indexing() -> None:
    compose = yaml.safe_load((ROOT / "infra/compose.yaml").read_text())
    services = compose["services"]

    assert services["index"]["command"] == ["python", "-m", "app.cli.index_embeddings"]
    assert services["index"]["depends_on"]["seed"]["condition"] == (
        "service_completed_successfully"
    )
    assert services["api"]["depends_on"]["index"]["condition"] == (
        "service_completed_successfully"
    )
