from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import workflow as workflow_routes
from app.api.workflow_schemas import TopicAnalysisItem, TopicAnalysisView
from app.core.tokens import StaffPrincipal


class _TopicService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get(self, **kwargs: Any) -> TopicAnalysisView:
        self.calls.append(("get", kwargs))
        return self._view(status="ready")

    async def analyze(self, **kwargs: Any) -> TopicAnalysisView:
        self.calls.append(("analyze", kwargs))
        return self._view(status="ready")

    @staticmethod
    def _view(*, status: str) -> TopicAnalysisView:
        return TopicAnalysisView(
            status=status,
            generated_at=datetime.now(UTC),
            period_days=30,
            question_count=12,
            analyzed_question_count=12,
            summary="客户主要关注赛事报名和项目孵化。",
            topics=[
                TopicAnalysisItem(
                    topic="赛事报名",
                    count=7,
                    share=0.5833,
                    sample_questions=["如何报名？"],
                )
            ],
            provider="deepseek",
            model="deepseek-chat",
        )


@pytest.fixture
def topic_client(monkeypatch: pytest.MonkeyPatch):
    service = _TopicService()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(workflow_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(workflow_routes, "_topic_service", lambda _request: service)
    with TestClient(app) as client:
        yield client, service, principal_box


def test_topic_analysis_get_and_analyze_forward_server_scope(topic_client) -> None:
    client, service, principal_box = topic_client

    response = client.get("/api/v1/admin/analytics/topics?period_days=30")
    assert response.status_code == 200
    assert response.json()["data"]["topics"][0]["topic"] == "赛事报名"
    get_call = service.calls[-1]
    assert get_call[0] == "get"
    assert get_call[1]["scope"].company_id == principal_box["value"].company_id
    assert get_call[1]["period_days"] == 30

    response = client.post("/api/v1/admin/analytics/topics:analyze?period_days=30")
    assert response.status_code == 200
    analyze_call = service.calls[-1]
    assert analyze_call[0] == "analyze"
    assert analyze_call[1]["scope"].tenant_id == principal_box["value"].tenant_id
    assert analyze_call[1]["period_days"] == 30


def test_topic_analysis_permissions_and_period_validation(topic_client) -> None:
    client, service, principal_box = topic_client
    principal_box["value"] = _principal(role="card_owner")
    assert client.get("/api/v1/admin/analytics/topics").status_code == 200
    assert service.calls[-1][1]["scope"].is_card_owner

    principal_box["value"] = _principal(
        role="staff",
        permissions=("conversations.read",),
    )
    assert client.post("/api/v1/admin/analytics/topics:analyze").status_code == 200

    principal_box["value"] = _principal(role="staff")
    assert client.get("/api/v1/admin/analytics/topics").status_code == 403

    principal_box["value"] = _principal(role="company_admin")
    assert client.get("/api/v1/admin/analytics/topics?period_days=91").status_code == 422


def test_topic_analysis_openapi_contract(topic_client) -> None:
    client, _service, _principal_box = topic_client
    paths = client.get("/openapi.json").json()["paths"]
    get_operation = paths["/api/v1/admin/analytics/topics"]["get"]
    analyze_operation = paths["/api/v1/admin/analytics/topics:analyze"]["post"]
    assert get_operation["operationId"] == "getAdminTopicAnalysis"
    assert analyze_operation["operationId"] == "analyzeAdminConversationTopics"
    assert get_operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("TopicAnalysisEnvelope")


def _principal(*, role: str, permissions: tuple[str, ...] = ()) -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role=role,
        permissions=permissions,
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )
