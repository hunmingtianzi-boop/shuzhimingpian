from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.platform_schemas import (
    EnterpriseListItem,
    PlatformAuditRecord,
    PlatformCardProjection,
    PlatformCompanyAggregate,
    PlatformEnterpriseDetail,
    PlatformEnterpriseLifecycleRecord,
    PlatformOverviewRecord,
    PlatformTaskRecord,
)
from app.api.routes import platform as platform_routes
from app.api.routes import platform_operations as operation_routes
from app.core.tokens import StaffPrincipal
from app.services import platform_store as platform_store_module


class RouteStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.company_id = uuid.uuid4()
        self.now = datetime.now(UTC)

    async def list_enterprises(
        self, **kwargs: Any
    ) -> tuple[list[EnterpriseListItem], int]:
        self.calls.append(("list", kwargs))
        return [
            EnterpriseListItem(
                tenant_id=uuid.uuid4(),
                tenant_slug="acme",
                tenant_name="Acme 集团",
                company_id=self.company_id,
                company_name="Acme 商务",
                status="active",
                created_at=self.now,
            )
        ], 1

    async def get_overview(self, **kwargs: Any) -> PlatformOverviewRecord:
        self.calls.append(("overview", kwargs))
        return PlatformOverviewRecord(
            generated_at=self.now,
            enterprise_count=1,
            active_enterprise_count=1,
            onboarding_count=0,
            published_card_count=1,
            visits_30d=8,
            conversations_30d=3,
            leads_30d=1,
            failed_task_count=0,
            llm_ready=True,
            import_ready=True,
        )

    async def get_enterprise_detail(self, **kwargs: Any) -> PlatformEnterpriseDetail:
        self.calls.append(("detail", kwargs))
        return PlatformEnterpriseDetail(
            tenant_id=uuid.uuid4(),
            tenant_slug="acme",
            tenant_name="Acme 集团",
            company_id=self.company_id,
            company_name="Acme 商务",
            status="active",
            version=3,
            onboarding_status="completed",
            profile_completion=100,
            employee_count=2,
            card_count=2,
            published_card_count=1,
            visits_30d=8,
            conversations_30d=3,
            leads_30d=1,
            cards=[
                PlatformCardProjection(
                    id=uuid.uuid4(),
                    card_kind="enterprise",
                    display_name="已发布名片",
                    title="销售总监",
                    status="published",
                    updated_at=self.now,
                    share_url="https://cards.example/c/published-card",
                ),
                PlatformCardProjection(
                    id=uuid.uuid4(),
                    card_kind="employee",
                    display_name="草稿名片",
                    title="顾问",
                    status="draft",
                    updated_at=self.now,
                    share_url=None,
                ),
            ],
            created_at=self.now,
            updated_at=self.now,
        )

    async def list_company_aggregates(
        self, **kwargs: Any
    ) -> tuple[list[PlatformCompanyAggregate], int]:
        self.calls.append(("aggregates", kwargs))
        return [
            PlatformCompanyAggregate(
                company_id=self.company_id,
                company_name="Acme 商务",
                employee_count=2,
                visits_30d=8,
                unique_visitors_30d=5,
                last_visit_at=self.now,
            )
        ], 1

    async def list_tasks(self, **kwargs: Any) -> tuple[list[PlatformTaskRecord], int]:
        self.calls.append(("tasks", kwargs))
        return [
            PlatformTaskRecord(
                id=uuid.uuid4(),
                task_type="knowledge_import",
                business_label="资料导入",
                status="failed",
                company_id=self.company_id,
                company_name="Acme 商务",
                error_code="IMPORT_FAILED",
                created_at=self.now,
                updated_at=self.now,
            )
        ], 1

    async def list_audit(self, **kwargs: Any) -> tuple[list[PlatformAuditRecord], int]:
        self.calls.append(("audit", kwargs))
        return [
            PlatformAuditRecord(
                id=uuid.uuid4(),
                actor_display_name="平台管理员",
                action="platform.onboarding.confirm",
                business_label="确认资料建企",
                resource_type="platform_onboarding_session",
                resource_id=uuid.uuid4(),
                result="recorded",
                created_at=self.now,
            )
        ], 1

    async def transition_enterprise(
        self, **kwargs: Any
    ) -> PlatformEnterpriseLifecycleRecord:
        self.calls.append(("transition", kwargs))
        return PlatformEnterpriseLifecycleRecord(
            tenant_id=uuid.uuid4(),
            company_id=self.company_id,
            previous_status="active",
            status="suspended",
            version=4,
            changed=True,
            updated_at=self.now,
        )


def test_platform_share_base_requires_explicit_opt_in_for_remote_http() -> None:
    public_base = "http://47.83.235.176"

    with pytest.raises(ValueError, match="must use HTTPS"):
        platform_store_module._normalize_public_card_base_url(public_base)

    assert (
        platform_store_module._normalize_public_card_base_url(
            public_base,
            allow_insecure_http=True,
        )
        == public_base
    )


def _principal(role: str) -> StaffPrincipal:
    return StaffPrincipal(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        role=role,
        permissions=(),
        session_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
    )


@pytest.fixture
def route_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RouteStore, dict[str, StaffPrincipal]]:
    store = RouteStore()
    principal_box = {"value": _principal("platform_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(platform_routes.router, prefix="/api/v1")
    app.include_router(operation_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(platform_routes, "_store", lambda _request: store)
    monkeypatch.setattr(operation_routes, "_store", lambda _request: store)
    async def healthy_probe(service: str, operation: object):
        if hasattr(operation, "close"):
            operation.close()
        return operation_routes.PlatformServiceHealthRecord(
            service=service,
            status="healthy",
            checked_at=datetime.now(UTC),
            latency_ms=0,
        )
    monkeypatch.setattr(operation_routes, "_probe", healthy_probe)
    with TestClient(app) as client:
        yield client, store, principal_box


def test_platform_operations_expose_only_the_frozen_read_surface(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _ = route_client
    paths = client.app.openapi()["paths"]

    assert paths["/api/v1/platform/overview"]["get"]["operationId"] == "getPlatformOverview"
    assert (
        paths["/api/v1/platform/enterprises/{company_id}"]["get"]["operationId"]
        == "getPlatformEnterpriseDetail"
    )
    assert set(paths["/api/v1/platform/enterprises"]) == {"get", "post"}
    assert set(paths["/api/v1/platform/enterprises/{company_id}/status"]) == {"put"}
    assert set(paths["/api/v1/platform/company-aggregates"]) == {"get"}
    assert set(paths["/api/v1/platform/tasks"]) == {"get"}
    assert set(paths["/api/v1/platform/audit"]) == {"get"}
    assert set(paths["/api/v1/platform/health"]) == {"get"}


def test_governance_projections_are_business_safe_and_paginated(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _ = route_client
    aggregates = client.get("/api/v1/platform/company-aggregates?limit=20&offset=0")
    tasks = client.get("/api/v1/platform/tasks?limit=20&offset=0")
    audit = client.get("/api/v1/platform/audit?limit=20&offset=0")

    assert aggregates.status_code == tasks.status_code == audit.status_code == 200
    assert aggregates.json()["data"][0]["employee_count"] == 2
    assert tasks.json()["data"][0]["business_label"] == "资料导入"
    assert audit.json()["data"][0]["actor_display_name"] == "平台管理员"
    serialized = "".join((aggregates.text, tasks.text, audit.text))
    for forbidden in ("visitor_email", "conversation_body", "raw_text", "api_key"):
        assert forbidden not in serialized


def test_list_forwards_bounded_search_status_and_pagination(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    response = client.get(
        "/api/v1/platform/enterprises",
        params={"search": " Acme ", "status": "active", "limit": 20, "offset": 5},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    call = next(payload for name, payload in store.calls if name == "list")
    assert call["search"] == "Acme"
    assert call["status"] == "active"
    assert call["limit"] == 20
    assert call["offset"] == 5


def test_overview_and_detail_return_allowlisted_projection(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    overview = client.get("/api/v1/platform/overview")
    detail = client.get(f"/api/v1/platform/enterprises/{store.company_id}")

    assert overview.status_code == 200
    assert set(overview.json()["data"]) == {
        "generated_at",
        "enterprise_count",
        "active_enterprise_count",
        "onboarding_count",
        "published_card_count",
        "visits_30d",
        "conversations_30d",
        "leads_30d",
        "failed_task_count",
        "llm_ready",
        "import_ready",
    }
    assert detail.status_code == 200
    payload = detail.json()["data"]
    assert payload["cards"][0]["card_kind"] == "enterprise"
    assert payload["cards"][1]["card_kind"] == "employee"
    assert payload["cards"][0]["share_url"].endswith("/c/published-card")
    assert payload["cards"][1]["share_url"] is None
    serialized = str(payload).casefold()
    for forbidden in ("email", "mobile", "conversation_body", "lead_body", "raw_text"):
        assert forbidden not in serialized


def test_overview_does_not_claim_import_ready_when_worker_probe_fails(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = route_client

    async def unavailable_worker(service: str, operation: object):
        if hasattr(operation, "close"):
            operation.close()
        return operation_routes.PlatformServiceHealthRecord(
            service=service,
            status="unavailable",
            checked_at=datetime.now(UTC),
            latency_ms=1,
            error_code="WORKER_UNAVAILABLE",
        )

    monkeypatch.setattr(operation_routes, "_probe", unavailable_worker)
    response = client.get("/api/v1/platform/overview")
    assert response.status_code == 200
    assert response.json()["data"]["import_ready"] is False


def test_lifecycle_transition_requires_reason_version_and_returns_no_private_data(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    response = client.put(
        f"/api/v1/platform/enterprises/{store.company_id}/status",
        json={
            "expected_version": 3,
            "target_status": "suspended",
            "reason": "合同到期，暂停企业访问",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "tenant_id": response.json()["data"]["tenant_id"],
        "company_id": str(store.company_id),
        "previous_status": "active",
        "status": "suspended",
        "version": 4,
        "changed": True,
        "updated_at": response.json()["data"]["updated_at"],
    }
    call = next(payload for name, payload in store.calls if name == "transition")
    assert call["expected_version"] == 3
    assert call["reason"] == "合同到期，暂停企业访问"
    assert "reason" not in response.text


def test_lifecycle_transition_rejects_missing_reason_before_store_access(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    response = client.put(
        f"/api/v1/platform/enterprises/{store.company_id}/status",
        json={"expected_version": 3, "target_status": "suspended"},
    )

    assert response.status_code == 422
    assert store.calls == []


def test_lifecycle_transition_rejects_non_platform_admin_before_store_access(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal_box["value"] = _principal("company_admin")

    response = client.put(
        f"/api/v1/platform/enterprises/{store.company_id}/status",
        json={
            "expected_version": 3,
            "target_status": "suspended",
            "reason": "合同到期",
        },
    )

    assert response.status_code == 403
    assert store.calls == []


@pytest.mark.parametrize("path", [
    "/api/v1/platform/overview",
    "/api/v1/platform/enterprises",
    "/api/v1/platform/company-aggregates",
    "/api/v1/platform/tasks",
    "/api/v1/platform/audit",
    "/api/v1/platform/health",
])
def test_non_platform_admin_is_rejected_before_store_access(
    path: str,
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal_box["value"] = _principal("company_admin")

    response = client.get(path)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert store.calls == []


def test_operations_migration_uses_narrow_security_definer_functions() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260715_0017_platform_operations_read_models.py"
    ).read_text(encoding="utf-8").casefold()

    assert migration.count("security definer") == 7
    assert migration.count("set search_path = ''") == 7
    assert migration.count("if not app.platform_actor_allowed()") == 7
    assert migration.count("revoke all on function") >= 7
    assert "grant execute on function app.platform_operations_" in migration
    assert "grant select" not in migration
    assert " from public.messages" not in migration
    assert " from public.visitors" not in migration
    assert "knowledge_versions" not in migration
    assert "requirement_ciphertext" not in migration
    assert "api_key_ciphertext" not in migration
    transition = migration.split(
        "create function app.platform_operations_transition_enterprise", 1
    )[1]
    assert ":audit" not in transition
    assert "pg_catalog.chr(58)" in transition


def test_all_platform_read_models_exclude_unconfirmed_provisional_enterprises() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260715_0017_platform_operations_read_models.py"
    ).read_text(encoding="utf-8").casefold()
    segments = (
        migration.split("create function app.platform_operations_overview", 1)[1].split(
            "create function app.platform_operations_enterprises", 1
        )[0],
        migration.split("create function app.platform_operations_enterprises", 1)[1].split(
            "create function app.platform_operations_enterprise_detail", 1
        )[0],
        migration.split("create function app.platform_operations_enterprise_detail", 1)[1],
    )

    for segment in segments:
        assert "tenant.settings ->> 'onboarding_status'" in segment
        assert "company.settings ->> 'onboarding_status'" in segment
        assert "<> 'provisional'" in segment
