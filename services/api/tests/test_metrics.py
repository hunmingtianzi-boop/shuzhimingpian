from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.metrics import MetricsRegistry
from app.main import create_app


def test_registry_renders_cumulative_histograms_and_ai_aggregates() -> None:
    registry = MetricsRegistry()
    registry.request_started()
    registry.request_finished(
        method="GET",
        route="/api/v1/public/cards/{slug}",
        status_code=200,
        duration_seconds=0.12,
    )
    registry.observe_ai_result(
        provider="deepseek",
        model="test-model",
        outcome="refusal",
        retrieval_mode="hybrid",
        duration_seconds=1.2,
        model_seconds=0.8,
        input_tokens=100,
        output_tokens=20,
        estimated_cost_cny=0.002,
        retrieval_count=5,
        citation_count=0,
        refusal_code="insufficient_evidence",
        query_complexity="compound",
        confidence_band="low",
        subquery_count=2,
        coverage_ratio=0.0,
    )
    registry.observe_first_token(source="generated", duration_seconds=1.1)

    rendered = registry.render()

    assert "cf_http_requests_in_flight 0" in rendered
    assert (
        'cf_http_requests_total{method="GET",route="/api/v1/public/cards/{slug}",'
        'status_class="2xx"} 1'
    ) in rendered
    assert 'cf_http_request_duration_seconds_bucket{method="GET"' in rendered
    assert 'le="0.25"' in rendered
    assert 'cf_ai_tokens_total{model="test-model",provider="deepseek",type="input"} 100' in rendered
    assert 'cf_ai_refusals_total{code="insufficient_evidence"} 1' in rendered
    assert (
        'cf_rag_queries_total{complexity="compound",confidence="low",outcome="refusal"} 1'
        in rendered
    )
    assert (
        'cf_rag_low_confidence_blocks_total{code="insufficient_evidence"} 1'
        in rendered
    )
    assert 'cf_ai_time_to_first_content_seconds_count{source="generated"} 1' in rendered


def test_metrics_endpoint_requires_configured_bearer_and_uses_route_templates() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            metrics_bearer_token="unit-test-metrics-secret",  # noqa: S106
        )
    )
    client = TestClient(app)

    unauthorized = client.get("/api/v1/metrics")
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"

    assert client.get("/api/v1/health/live").status_code == 200
    response = client.get(
        "/api/v1/metrics",
        headers={"Authorization": "Bearer unit-test-metrics-secret"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert 'route="/api/v1/health/live"' in response.text
    assert 'route="/api/v1/metrics"' in response.text
    assert "unit-test-metrics-secret" not in response.text


def test_local_metrics_endpoint_can_be_scraped_without_a_secret() -> None:
    app = create_app(Settings(_env_file=None, app_env="test"))
    response = TestClient(app).get("/api/v1/metrics")

    assert response.status_code == 200
