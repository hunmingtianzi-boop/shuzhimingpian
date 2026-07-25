from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.export_schemas import ExportAvailabilityView, ExportRequestView
from app.api.routes import exports as export_routes
from app.core.tokens import StaffPrincipal
from app.db.models import DataExportRequest, DataExportStatus, DataExportType
from app.services.export_store import ExportDownload, ExportStore


class ExportRouteStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.view = _view()

    async def create(self, **kwargs: Any) -> ExportRequestView:
        self.calls.append(("create", kwargs))
        self.view = self.view.model_copy(
            update={
                "export_type": kwargs["export_type"],
                "include_sensitive": kwargs["include_sensitive"],
            }
        )
        return self.view

    async def list(self, **kwargs: Any) -> tuple[list[ExportRequestView], int]:
        self.calls.append(("list", kwargs))
        return [self.view], 1

    async def availability(self, **kwargs: Any) -> ExportAvailabilityView:
        self.calls.append(("availability", kwargs))
        return ExportAvailabilityView(
            visitors=42,
            leads=0,
            conversations=42,
            generated_at=datetime.now(UTC),
        )

    async def get(self, **kwargs: Any) -> ExportRequestView:
        self.calls.append(("get", kwargs))
        return self.view

    async def download(self, **kwargs: Any) -> ExportDownload:
        self.calls.append(("download", kwargs))
        return ExportDownload(
            content="\ufeffid\r\nlead-1\r\n".encode(),
            file_name="leads.csv",
            content_type="text/csv; charset=utf-8",
        )


@pytest.fixture
def export_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, ExportRouteStore, dict[str, StaffPrincipal]]:
    store = ExportRouteStore()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(export_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(export_routes, "_store", lambda _request: store)
    with TestClient(app) as client:
        yield client, store, principal_box


def test_create_export_forwards_server_derived_scope(
    export_client: tuple[TestClient, ExportRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = export_client
    response = client.post(
        "/api/v1/admin/exports/leads",
        headers={"Idempotency-Key": "export-request-001"},
        json={"include_sensitive": True},
    )
    assert response.status_code == 202
    call = store.calls[-1]
    assert call[0] == "create"
    assert call[1]["scope"].tenant_id == principal_box["value"].tenant_id
    assert call[1]["scope"].company_id == principal_box["value"].company_id
    assert call[1]["scope"].actor_user_id == principal_box["value"].user_id
    assert call[1]["export_type"] == "leads"
    assert call[1]["include_sensitive"] is True


def test_sensitive_export_is_denied_to_card_owner(
    export_client: tuple[TestClient, ExportRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = export_client
    principal_box["value"] = _principal(role="card_owner")
    response = client.post(
        "/api/v1/admin/exports/leads",
        headers={"Idempotency-Key": "export-request-002"},
        json={"include_sensitive": True},
    )
    assert response.status_code == 403
    assert not store.calls


def test_non_admin_needs_dataset_permission(
    export_client: tuple[TestClient, ExportRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = export_client
    principal_box["value"] = _principal(role="auditor")
    denied = client.post(
        "/api/v1/admin/exports/conversations",
        headers={"Idempotency-Key": "export-request-003"},
        json={},
    )
    assert denied.status_code == 403
    principal_box["value"] = _principal(
        role="auditor", permissions=("conversations.read",)
    )
    allowed = client.post(
        "/api/v1/admin/exports/conversations",
        headers={"Idempotency-Key": "export-request-004"},
        json={},
    )
    assert allowed.status_code == 202
    assert store.calls[-1][1]["export_type"] == "conversations"


def test_download_uses_authenticated_store_and_no_store_headers(
    export_client: tuple[TestClient, ExportRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = export_client
    response = client.get(f"/api/v1/admin/exports/{store.view.id}/download")
    assert response.status_code == 200
    assert response.content.startswith("\ufeff".encode())
    assert response.headers["cache-control"] == "private, no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert [call[0] for call in store.calls] == ["get", "download"]


def test_availability_exposes_real_exportable_counts(
    export_client: tuple[TestClient, ExportRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = export_client
    response = client.get("/api/v1/admin/exports/availability")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["visitors"] == 42
    assert payload["leads"] == 0
    assert payload["conversations"] == 42
    assert payload["generated_at"]
    call = store.calls[-1]
    assert call[0] == "availability"
    assert call[1]["scope"].company_id == principal_box["value"].company_id


def test_expired_record_clears_ciphertext_and_reports_expired() -> None:
    now = datetime.now(UTC)
    record = DataExportRequest(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        requested_by=uuid.uuid4(),
        requested_role="company_admin",
        export_type=DataExportType.LEADS,
        status=DataExportStatus.COMPLETED,
        scope_kind="company",
        include_sensitive=False,
        outbox_event_id=uuid.uuid4(),
        file_name="leads.csv",
        content_type="text/csv; charset=utf-8",
        file_ciphertext=b"encrypted",
        file_sha256="a" * 64,
        row_count=1,
        completed_at=now - timedelta(hours=25),
        expires_at=now - timedelta(seconds=1),
        created_at=now - timedelta(hours=26),
        updated_at=now,
    )
    ExportStore._expire_record(record)
    assert record.status == DataExportStatus.EXPIRED
    assert record.file_ciphertext is None


def _principal(
    *,
    role: str,
    permissions: tuple[str, ...] = (),
) -> StaffPrincipal:
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


def _view() -> ExportRequestView:
    return ExportRequestView(
        id=uuid.uuid4(),
        export_type="leads",
        status="completed",
        include_sensitive=False,
        row_count=1,
        file_name="leads.csv",
        content_type="text/csv; charset=utf-8",
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
