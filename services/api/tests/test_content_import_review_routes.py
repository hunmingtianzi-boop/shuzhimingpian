from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.content_import_schemas import (
    ContentImportCandidateRecord,
    ContentImportRunRecord,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import knowledge_ops
from app.core.tokens import StaffPrincipal


def _principal(*, permissions: tuple[str, ...] = ()) -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role="card_owner",
        permissions=permissions,
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )


class _ReviewService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.candidate = ContentImportCandidateRecord(
            id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            category="products",
            payload={
                "name": "智能名片",
                "category": "企业服务",
                "summary": "统一展示企业资料",
                "detail": "连接业务资料与员工身份",
                "audience": "企业客户",
                "price_boundary": "",
            },
            source_id="item-1",
            source_text="智能名片统一展示企业资料",
            confidence=0.91,
            status="pending_review",
            version=1,
            created_at=now,
            updated_at=now,
        )
        self.run = ContentImportRunRecord(
            id=self.candidate.run_id,
            batch_id=uuid.uuid4(),
            status="review",
            provider="deepseek",
            model="deepseek-chat",
            attempts=1,
            counts={"products": 1},
            candidates=[self.candidate],
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def generate(self, **kwargs: Any) -> ContentImportRunRecord:
        self.calls.append(("generate", kwargs))
        return self.run

    async def list_runs(self, **kwargs: Any) -> list[ContentImportRunRecord]:
        return [self.run]

    async def get_run(self, **kwargs: Any) -> ContentImportRunRecord:
        return self.run

    async def get_candidate(self, **kwargs: Any) -> ContentImportCandidateRecord:
        return self.candidate

    async def accept_candidate(self, **kwargs: Any) -> ContentImportCandidateRecord:
        self.calls.append(("accept", kwargs))
        return self.candidate.model_copy(update={"status": "accepted", "version": 2})


def _client(monkeypatch: Any, principal: StaffPrincipal) -> tuple[TestClient, _ReviewService]:
    service = _ReviewService()
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(knowledge_ops.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal
    app.state.content_import_review_service = service
    app.state.catalog_store = object()
    monkeypatch.setattr(knowledge_ops, "_admin_store", lambda _request: object())
    return TestClient(app), service


def test_generate_returns_reviewable_candidates(monkeypatch: Any) -> None:
    client, service = _client(monkeypatch, _principal(permissions=("knowledge.write",)))
    with client:
        response = client.post(
            "/api/v1/admin/content-import-runs",
            json={"batch_id": str(service.run.batch_id)},
        )
    assert response.status_code == 201
    assert response.json()["data"]["candidates"][0]["category"] == "products"
    assert service.calls[0][1]["retry"] is False


def test_generate_forwards_explicit_safe_retry(monkeypatch: Any) -> None:
    client, service = _client(monkeypatch, _principal(permissions=("knowledge.write",)))
    with client:
        response = client.post(
            "/api/v1/admin/content-import-runs",
            json={"batch_id": str(service.run.batch_id), "retry": True},
        )
    assert response.status_code == 201
    assert service.calls[0][1]["retry"] is True


def test_accept_requires_permission_for_candidate_category(monkeypatch: Any) -> None:
    principal = _principal(permissions=("knowledge.write",))
    client, service = _client(monkeypatch, principal)
    with client:
        denied = client.post(
            f"/api/v1/admin/content-import-candidates/{service.candidate.id}/accept",
            json={"expected_version": 1, "apply_fields": []},
        )
    assert denied.status_code == 403

    client, service = _client(monkeypatch, _principal(permissions=("catalog.write",)))
    with client:
        accepted = client.post(
            f"/api/v1/admin/content-import-candidates/{service.candidate.id}/accept",
            json={"expected_version": 1, "apply_fields": []},
        )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["status"] == "accepted"
