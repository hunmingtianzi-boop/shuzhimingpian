from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.knowledge_import_schemas import KnowledgeImportBatchRecord
from app.api.platform_schemas import (
    PlatformOnboardingImportStatusRecord,
    PlatformOnboardingSessionRecord,
)
from app.api.routes import platform_onboarding as routes
from app.core.tokens import StaffPrincipal
from app.services.knowledge_import_store import KnowledgeImportScope
from app.services.platform_onboarding import (
    _BUSINESS_PROFILE_FIELDS,
    _SUGGESTION_SYSTEM_PROMPT,
    PlatformOnboardingImportScope,
    PlatformOnboardingService,
    _parse_suggestions,
)


def _principal(role: str = "platform_admin") -> StaffPrincipal:
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


class RouteService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.record = PlatformOnboardingSessionRecord(
            id=uuid.uuid4(),
            status="draft",
            tenant_slug="acme-demo",
            tenant_name="Acme",
            admin_account="admin@acme.test",
            admin_display_name="Acme Admin",
            initial_card_display_name="Acme",
            initial_card_title="Acme Official Card",
            version=1,
            expires_at=now + timedelta(hours=24),
            created_at=now,
            updated_at=now,
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def start(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("start", kwargs))
        return self.record

    async def list_sessions(
        self, **kwargs: Any
    ) -> tuple[list[PlatformOnboardingSessionRecord], int]:
        self.calls.append(("list", kwargs))
        return [self.record], 1

    async def get_session(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("get", kwargs))
        return self.record

    async def get_import_status(
        self, **kwargs: Any
    ) -> PlatformOnboardingImportStatusRecord:
        self.calls.append(("import_status", kwargs))
        return PlatformOnboardingImportStatusRecord(
            session_id=self.record.id,
            settled=True,
            batches=[],
        )

    async def import_scope(self, **kwargs: Any) -> PlatformOnboardingImportScope:
        self.calls.append(("scope", kwargs))
        return PlatformOnboardingImportScope(
            session_id=self.record.id,
            version=self.record.version,
            scope=KnowledgeImportScope(
                tenant_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                actor_user_id=uuid.uuid4(),
            ),
        )

    async def attach_import_batch(
        self, **kwargs: Any
    ) -> PlatformOnboardingSessionRecord:
        self.calls.append(("attach", kwargs))
        return self.record.model_copy(
            update={"status": "processing", "version": 2}
        )

    async def generate_suggestions(
        self, **kwargs: Any
    ) -> PlatformOnboardingSessionRecord:
        self.calls.append(("suggestions", kwargs))
        return self.record.model_copy(update={"status": "manual_required", "version": 2})

    async def confirm(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("confirm", kwargs))
        return self.record.model_copy(update={"status": "confirmed", "version": 2})

    async def cancel(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("cancel", kwargs))
        return self.record.model_copy(update={"status": "cancelled", "version": 2})

    async def update_content_candidate(self, **kwargs: Any) -> Any:
        self.calls.append(("candidate.update", kwargs))
        body = kwargs["body"]
        return {
            "id": kwargs["candidate_id"],
            "run_id": uuid.uuid4(),
            "category": body.category,
            "payload": body.payload,
            "source_id": str(uuid.uuid4()),
            "source_text": "企业原文证据",
            "confidence": 0.8,
            "status": "pending_review",
            "version": body.expected_version + 1,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }

    async def ignore_content_candidate(self, **kwargs: Any) -> Any:
        self.calls.append(("candidate.ignore", kwargs))
        return {
            "id": kwargs["candidate_id"],
            "run_id": uuid.uuid4(),
            "category": "unclassified",
            "payload": {"text": "企业原文证据", "reason": "人工忽略"},
            "source_id": str(uuid.uuid4()),
            "source_text": "企业原文证据",
            "confidence": 0.8,
            "status": "ignored",
            "version": kwargs["expected_version"] + 1,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }


class ImportStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.batch_id = uuid.uuid4()

    async def create_batch(self, **kwargs: Any) -> KnowledgeImportBatchRecord:
        self.calls.append(kwargs)
        return KnowledgeImportBatchRecord(
            id=self.batch_id,
            status="pending",
            total_items=1,
            pending_items=1,
            succeeded_items=0,
            failed_items=0,
            created_at=datetime.now(UTC),
        )


@pytest.fixture
def route_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]]:
    service = RouteService()
    import_store = ImportStore()
    principal_box = {"value": _principal()}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(routes, "_service", lambda _request: service)
    monkeypatch.setattr(routes, "_import_store", lambda _request: import_store)
    with TestClient(app) as client:
        yield client, service, import_store, principal_box


def test_route_surface_is_session_bound(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _, _ = route_client
    paths = client.app.openapi()["paths"]
    root = "/api/v1/platform/onboarding"
    assert set(paths[root]) == {"get", "post"}
    assert set(paths[f"{root}/{{onboarding_id}}"] ) == {"get"}
    for suffix in ("suggestions", "confirm", "cancel"):
        assert set(paths[f"{root}/{{onboarding_id}}/{suffix}"]) == {"post"}
    assert set(paths[f"{root}/{{onboarding_id}}/imports"]) == {"get", "post"}
    assert set(paths[f"{root}/{{onboarding_id}}/candidates/{{candidate_id}}"]) == {"put"}
    assert set(paths[f"{root}/{{onboarding_id}}/candidates/{{candidate_id}}/ignore"]) == {"post"}
    upload = paths[f"{root}/{{onboarding_id}}/imports"]["post"]
    serialized = str(upload)
    assert "tenant_id" not in serialized
    assert "company_id" not in serialized


def test_import_progress_resolves_scope_from_session_only(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, _, _ = route_client
    response = client.get(
        f"/api/v1/platform/onboarding/{service.record.id}/imports"
    )
    assert response.status_code == 200
    assert response.json()["data"] == {
        "session_id": str(service.record.id),
        "settled": True,
        "batches": [],
    }
    call = next(payload for name, payload in service.calls if name == "import_status")
    assert call["onboarding_id"] == service.record.id
    assert "tenant_id" not in call
    assert "company_id" not in call


def test_open_session_review_projection_never_includes_a_password(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, _, _ = route_client
    response = client.get(f"/api/v1/platform/onboarding/{service.record.id}")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["admin_account"] == "admin@acme.test"
    assert payload["admin_display_name"] == "Acme Admin"
    assert payload["initial_card_display_name"] == "Acme"
    assert payload["initial_card_title"] == "Acme Official Card"
    assert "admin_password" not in payload


@pytest.mark.asyncio
async def test_session_lookup_query_is_bound_to_the_creating_platform_admin() -> None:
    actor_user_id = uuid.uuid4()

    class CaptureSession:
        statement: Any = None

        async def scalar(self, statement: Any) -> None:
            self.statement = statement
            return None

    session = CaptureSession()
    with pytest.raises(ApiError) as missing:
        await PlatformOnboardingService._row(  # noqa: SLF001 - security regression test
            session,  # type: ignore[arg-type]
            uuid.uuid4(),
            actor_user_id=actor_user_id,
        )

    assert missing.value.status_code == 404
    assert missing.value.code == "RESOURCE_NOT_FOUND"
    statement = str(session.statement)
    assert "platform_onboarding_sessions.id" in statement
    assert "platform_onboarding_sessions.created_by" in statement
    assert actor_user_id in session.statement.compile().params.values()


@pytest.mark.parametrize("status", ["confirmed", "cancelled", "expired", "failed"])
def test_terminal_session_is_rejected_before_import_details_are_loaded(status: str) -> None:
    with pytest.raises(ApiError) as closed:
        PlatformOnboardingService._require_open(  # noqa: SLF001 - security regression test
            type("OnboardingRow", (), {"status": status})()
        )
    assert closed.value.status_code == 409
    assert closed.value.code == "ONBOARDING_SESSION_CLOSED"


def test_upload_reuses_current_import_store_and_forces_draft(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, import_store, _ = route_client
    response = client.post(
        f"/api/v1/platform/onboarding/{service.record.id}/imports",
        files={"files": ("company.txt", "企业资料", "text/plain")},
    )
    assert response.status_code == 202
    assert import_store.calls[0]["auto_publish"] is False
    assert len(import_store.calls[0]["items"]) == 1
    assert import_store.calls[0]["scope"].tenant_id is not None
    attach = next(payload for name, payload in service.calls if name == "attach")
    assert attach["expected_version"] == service.record.version
    assert attach["batch_id"] == import_store.batch_id


def test_enterprise_actor_is_rejected_before_any_service_access(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, import_store, principal_box = route_client
    principal_box["value"] = _principal("company_admin")
    response = client.get("/api/v1/platform/onboarding")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert service.calls == []
    assert import_store.calls == []


def test_suggestion_parser_drops_unknown_unbound_and_duplicate_fields() -> None:
    source_id = uuid.uuid4()
    rows = {
        source_id: {
            "file_name": "company.txt",
            "document_id": uuid.uuid4(),
            "raw_text": "Acme 是制造企业。",
        }
    }
    suggestions = _parse_suggestions(
        {
            "suggestions": [
                {
                    "field": "company_name",
                    "value": "Acme",
                    "confidence": 1.4,
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "company_name",
                    "value": "重复项",
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "api_key",
                    "value": "should-never-pass",
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "summary",
                    "value": "无来源",
                    "source_ids": [str(uuid.uuid4())],
                },
            ]
        },
        source_rows=rows,
    )
    assert [item.field for item in suggestions] == ["company_name"]
    assert suggestions[0].confidence == 1
    assert suggestions[0].sources[0].import_item_id == source_id
    assert "api_key" not in str(suggestions)


def test_business_profile_parser_keeps_only_sourced_allowed_insights() -> None:
    source_id = uuid.uuid4()
    rows = {
        source_id: {
            "file_name": "业务介绍.pdf",
            "document_id": uuid.uuid4(),
            "raw_text": "为制造企业提供设备预测性维护服务。",
        }
    }
    profile = _parse_suggestions(
        {
            "business_profile": [
                {
                    "field": "business_positioning",
                    "value": "面向制造企业的设备预测性维护服务商",
                    "confidence": 0.92,
                    "source_ids": [str(source_id)],
                },
                {
                    "field": "annual_revenue",
                    "value": "1 亿元",
                    "source_ids": [str(source_id)],
                },
            ]
        },
        source_rows=rows,
        key="business_profile",
        allowed_fields={"business_positioning": 800},
    )
    assert [item.field for item in profile] == ["business_positioning"]
    assert profile[0].sources[0].file_name == "业务介绍.pdf"
    assert "annual_revenue" not in str(profile)


def test_business_analysis_contract_covers_directions_conflicts_and_evidence_gaps() -> None:
    assert {
        "core_capabilities",
        "business_model",
        "business_directions",
        "evidence_conflicts",
        "missing_information",
    }.issubset(_BUSINESS_PROFILE_FIELDS)
    assert "当前已有业务" in _SUGGESTION_SYSTEM_PROMPT
    assert "规划方向" in _SUGGESTION_SYSTEM_PROMPT
    assert "多份资料相互冲突" in _SUGGESTION_SYSTEM_PROMPT
    assert "禁止输出空话" in _SUGGESTION_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_settled_import_reconciles_processing_session_for_recovery() -> None:
    class ScalarSession:
        flushed = False
        refreshed = False

        async def scalar(self, _statement: object, _params: object = None) -> bool:
            return True

        async def flush(self) -> None:
            self.flushed = True

        async def refresh(self, refreshed_row: object) -> None:
            assert refreshed_row is row
            self.refreshed = True

    session = ScalarSession()
    row = type(
        "OnboardingRow",
        (),
        {
            "status": "processing",
            "import_batch_ids": [uuid.uuid4()],
            "version": 2,
            "id": uuid.uuid4(),
        },
    )()
    changed = await PlatformOnboardingService._reconcile_import_state(  # noqa: SLF001
        session, row  # type: ignore[arg-type]
    )
    assert changed is True
    assert row.status == "manual_required"
    assert row.version == 3
    assert session.flushed is True
    assert session.refreshed is True


@pytest.mark.asyncio
async def test_unsettled_import_keeps_processing_session_unchanged() -> None:
    class ScalarSession:
        async def scalar(self, _statement: object, _params: object = None) -> bool:
            return False

        async def flush(self) -> None:
            raise AssertionError("unsettled session must not flush")

    row = type(
        "OnboardingRow",
        (),
        {
            "status": "processing",
            "import_batch_ids": [uuid.uuid4()],
            "version": 2,
            "id": uuid.uuid4(),
        },
    )()
    changed = await PlatformOnboardingService._reconcile_import_state(  # noqa: SLF001
        ScalarSession(), row  # type: ignore[arg-type]
    )
    assert changed is False
    assert row.status == "processing"
    assert row.version == 2


def test_migration_stores_no_plain_password_and_has_narrow_draft_functions() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20260715_0018_platform_onboarding_sessions.py"
    ).read_text(encoding="utf-8")
    assert "admin_password" not in migration
    assert "api_key" not in migration
    assert "platform_onboarding_drafts" in migration
    assert "platform_onboarding_imports_settled" in migration
    assert "SECURITY DEFINER" in migration
    assert "SET search_path = ''" in migration
    assert "REVOKE ALL ON FUNCTION" in migration
    assert "item.batch_id = ANY(onboarding.import_batch_ids)" in migration


def test_owner_scope_migration_protects_rows_resources_and_security_definer_reads() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20260717_0022_platform_onboarding_owner_scope.py"
    ).read_text(encoding="utf-8")
    owner_predicate = (
        "created_by = NULLIF(current_setting('app.user_id', true), '')::uuid"
    )
    assert owner_predicate in migration
    assert "onboarding.created_by = " in migration
    assert "platform_onboarding_platform_only" in migration
    assert "platform_onboarding_imports_settled" in migration
    assert "platform_onboarding_drafts" in migration
    assert "SECURITY DEFINER" in migration
