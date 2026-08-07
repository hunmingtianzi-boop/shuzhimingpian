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
from app.api.workflow_schemas import VisitDetail, VisitPageDuration, VisitQuestion
from app.core.tokens import StaffPrincipal


class _VisitStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def get_visit_detail(self, **kwargs: Any) -> VisitDetail:
        self.calls.append(kwargs)
        now = datetime.now(UTC)
        visit_id = kwargs["visit_id"]
        return VisitDetail(
            id=visit_id,
            card_id=uuid.uuid4(),
            card_display_name="夜霜曦雪",
            visitor_id=uuid.uuid4(),
            source="card_web",
            started_at=now,
            ended_at=now,
            duration_seconds=18,
            conversation_count=1,
            event_count=3,
            page_durations=[
                VisitPageDuration(
                    page_key="company:overview",
                    page_title="企业页·overview",
                    object_type="card",
                    object_id="company:overview",
                    duration_seconds=12.5,
                    view_count=1,
                    last_viewed_at=now,
                )
            ],
            questions=[
                VisitQuestion(
                    message_id=uuid.uuid4(),
                    conversation_id=uuid.uuid4(),
                    question="夜霜是什么？",
                    asked_at=now,
                    answer_status="completed",
                )
            ],
        )


@pytest.fixture
def visit_client(monkeypatch: pytest.MonkeyPatch):
    store = _VisitStore()
    principal = StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role="company_admin",
        permissions=(),
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(workflow_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal
    monkeypatch.setattr(workflow_routes, "_store", lambda _request: store)
    with TestClient(app) as client:
        yield client, store, principal


def test_visit_detail_returns_page_durations_and_questions(visit_client) -> None:
    client, store, principal = visit_client
    visit_id = uuid.uuid4()

    response = client.get(f"/api/v1/admin/visits/{visit_id}")

    assert response.status_code == 200
    assert response.json()["data"]["page_durations"][0]["duration_seconds"] == 12.5
    assert response.json()["data"]["questions"][0]["question"] == "夜霜是什么？"
    assert store.calls[0]["visit_id"] == visit_id
    assert store.calls[0]["scope"].company_id == principal.company_id


def test_visit_detail_openapi_contract(visit_client) -> None:
    client, _, _ = visit_client
    operation = client.get("/openapi.json").json()["paths"][
        "/api/v1/admin/visits/{visit_id}"
    ]["get"]
    assert operation["operationId"] == "getAdminVisitDetail"
