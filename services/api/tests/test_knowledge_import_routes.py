from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.knowledge_import_schemas import KnowledgeImportBatchRecord
from app.api.routes import knowledge_ops
from app.core.tokens import StaffPrincipal
from app.services.knowledge_import_store import (
    KnowledgeImportScope,
    KnowledgeImportStore,
    _batch_display_name,
)


class _Store:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.record = KnowledgeImportBatchRecord(
            id=uuid.uuid4(),
            status="pending",
            total_items=1,
            pending_items=1,
            succeeded_items=0,
            failed_items=0,
            created_at=datetime.now(UTC),
        )

    async def create_batch(self, **kwargs: Any) -> KnowledgeImportBatchRecord:
        self.calls.append(("create", kwargs))
        return self.record.model_copy(
            update={"total_items": len(kwargs["items"]), "pending_items": len(kwargs["items"])}
        )

    async def get_batch(self, **kwargs: Any) -> KnowledgeImportBatchRecord:
        self.calls.append(("get", kwargs))
        return self.record

    async def list_batches(self, **kwargs: Any):
        self.calls.append(("list", kwargs))
        return [self.record], 1

    async def rename_batch(self, **kwargs: Any) -> KnowledgeImportBatchRecord:
        self.calls.append(("rename", kwargs))
        return self.record.model_copy(
            update={
                "display_name": kwargs["display_name"],
                "version": kwargs["expected_version"] + 1,
            }
        )


def _principal(role: str, permissions: tuple[str, ...] = ()) -> StaffPrincipal:
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


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    store = _Store()
    principal = {"value": _principal("company_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(knowledge_ops.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal["value"]
    monkeypatch.setattr(knowledge_ops, "_import_store", lambda _request: store)
    with TestClient(app) as test_client:
        yield test_client, store, principal


def test_csv_upload_is_encrypted_and_queued_without_request_thread_parsing(client) -> None:
    test_client, store, _ = client
    response = test_client.post(
        "/api/v1/admin/knowledge/imports",
        files={
            "files": (
                "bulk.csv",
                "title,raw_text,visibility\nA,正文一,public\nB,正文二,internal\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 202
    assert response.json()["data"]["total_items"] == 1
    assert len(store.calls[0][1]["items"]) == 1
    queued = store.calls[0][1]["items"][0]
    assert queued.source_type == "csv"
    assert "正文一".encode() in queued.payload


def test_upload_accepts_explicit_auto_publish_flag(client) -> None:
    test_client, store, _ = client
    response = test_client.post(
        "/api/v1/admin/knowledge/imports",
        data={"auto_publish": "true"},
        files={"files": ("note.txt", "最新产品资料", "text/plain")},
    )
    assert response.status_code == 202
    assert store.calls[0][1]["auto_publish"] is True


def test_upload_accepts_display_name_and_batch_can_be_renamed(client) -> None:
    test_client, store, _ = client
    response = test_client.post(
        "/api/v1/admin/knowledge/imports",
        data={"display_name": "星澜企业产品资料"},
        files={"files": ("note.txt", "最新产品资料", "text/plain")},
    )
    assert response.status_code == 202
    assert store.calls[0][1]["display_name"] == "星澜企业产品资料"

    response = test_client.patch(
        f"/api/v1/admin/knowledge/imports/{store.record.id}",
        json={"display_name": "星澜企业产品与案例资料", "expected_version": 1},
    )
    assert response.status_code == 200
    assert response.json()["data"]["display_name"] == "星澜企业产品与案例资料"
    assert store.calls[-1][0] == "rename"


def test_upload_rejects_unsupported_file_and_missing_permission(client) -> None:
    test_client, _, principal = client
    response = test_client.post(
        "/api/v1/admin/knowledge/imports",
        files={"files": ("script.exe", b"MZ", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IMPORT_UNSUPPORTED_TYPE"

    principal["value"] = _principal("card_owner", ("knowledge.read",))
    response = test_client.post(
        "/api/v1/admin/knowledge/imports",
        files={"files": ("bulk.csv", b"raw_text\ncontent\n", "text/csv")},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_import_store_sets_actor_in_rls_context(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def capture_scope(_session: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("app.services.knowledge_import_store.set_rls_context", capture_scope)
    scope = KnowledgeImportScope(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
    )
    await KnowledgeImportStore._set_scope(object(), scope)  # type: ignore[arg-type]

    assert captured == {
        "tenant_id": scope.tenant_id,
        "company_id": scope.company_id,
        "actor_user_id": scope.actor_user_id,
    }


def test_default_import_name_uses_company_date_and_sequence() -> None:
    assert (
        _batch_display_name(
            requested=None,
            company_name="星澜科技",
            created_at=datetime(2026, 8, 14, tzinfo=UTC),
            sequence_number=3,
        )
        == "星澜科技·资料导入·2026-08-14·第 3 次"
    )
    assert (
        _batch_display_name(
            requested="  自定义导入任务  ",
            company_name="星澜科技",
            created_at=datetime(2026, 8, 14, tzinfo=UTC),
            sequence_number=3,
        )
        == "自定义导入任务"
    )
