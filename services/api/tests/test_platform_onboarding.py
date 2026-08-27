from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.content_import_schemas import (
    ContentImportCandidateRecord,
    ContentImportRunRecord,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.knowledge_import_schemas import KnowledgeImportBatchRecord
from app.api.platform_schemas import (
    PlatformOnboardingImportStatusRecord,
    PlatformOnboardingSessionRecord,
    TemporaryCredentialDelivery,
)
from app.api.routes import platform_onboarding as routes
from app.core.tokens import StaffPrincipal
from app.services.knowledge_import_store import KnowledgeImportScope
from app.services.platform_onboarding import (
    _TERMINAL_IMPORT_REVIEW_SKIP_CODES,
    _BUSINESS_PROFILE_FIELDS,
    _MERGED_CANDIDATE_SYSTEM_PROMPT,
    PlatformOnboardingImportScope,
    PlatformOnboardingService,
    _decode_synthesis_payload,
    _default_onboarding_display_name,
    _fallback_merged_candidates,
    _fallback_synthesis_from_content_review,
    _merge_candidates_from_groups,
    _merge_content_reviews,
    _parse_merged_candidates,
    _parse_suggestions,
)


def test_only_terminal_unusable_import_errors_are_skippable() -> None:
    assert _TERMINAL_IMPORT_REVIEW_SKIP_CODES == {
        "IMPORT_BATCH_NOT_READY",
        "PARSED_DRAFT_MISSING",
    }
    assert "IMPORT_BATCH_NOT_FOUND" not in _TERMINAL_IMPORT_REVIEW_SKIP_CODES
    assert "LLM_RUNTIME_UNAVAILABLE" not in _TERMINAL_IMPORT_REVIEW_SKIP_CODES


@pytest.mark.parametrize(
    "answer",
    [
        '{"suggestions": [], "business_profile": []}',
        '```json\n{"suggestions": [], "business_profile": []}\n```',
        '分析结果如下：\n```JSON\n{"suggestions": [], "business_profile": []}\n```',
    ],
)
def test_decode_synthesis_payload_accepts_bare_or_fenced_json(answer: str) -> None:
    assert _decode_synthesis_payload(answer) == {
        "suggestions": [],
        "business_profile": [],
    }


def test_decode_synthesis_payload_rejects_non_json_answer() -> None:
    with pytest.raises(ValueError, match="synthesis_answer_not_json_object"):
        _decode_synthesis_payload("无法形成结构化结果")


def test_merge_content_reviews_keeps_candidates_from_every_source_batch() -> None:
    now = datetime.now(UTC)
    first_run_id = uuid.uuid4()
    second_run_id = uuid.uuid4()

    def review(run_id: uuid.UUID, batch_id: uuid.UUID, source_id: str) -> ContentImportRunRecord:
        return ContentImportRunRecord(
            id=run_id,
            batch_id=batch_id,
            status="review",
            provider="deepseek",
            model="flash",
            attempts=1,
            counts={"pending_review": 1},
            stage="completed",
            stage_message="候选等待确认",
            progress_current=1,
            progress_total=1,
            job_attempts=1,
            candidates=[
                ContentImportCandidateRecord(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    category="products",
                    payload={"name": source_id},
                    source_id=source_id,
                    source_text=f"{source_id} evidence",
                    confidence=0.9,
                    status="pending_review",
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            ],
            started_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )

    merged = _merge_content_reviews(
        [
            review(first_run_id, uuid.uuid4(), "file-one"),
            review(second_run_id, uuid.uuid4(), "file-two"),
        ]
    )

    assert merged is not None
    assert merged.status == "review"
    assert merged.counts == {"pending_review": 2}
    assert {candidate.source_id for candidate in merged.candidates} == {"file-one", "file-two"}
    assert merged.stage_message == "已完成 2 份资料分析，共生成 2 条候选"


def test_synthesis_fallback_groups_candidates_and_keeps_real_sources() -> None:
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    batch_id = uuid.uuid4()
    source_id = uuid.uuid4()
    categories = (
        ("products", {"name": "机器人蛋糕", "summary": "按需制作"}),
        ("case_studies", {"title": "甜品节", "result": "完成联合展示"}),
        ("faqs", {"question": "如何制作？", "answer": "由机器人协作完成"}),
    )
    review = ContentImportRunRecord(
        id=run_id,
        batch_id=batch_id,
        status="review",
        provider="deepseek",
        model="flash",
        attempts=1,
        counts={"pending_review": len(categories)},
        stage="completed",
        stage_message="候选等待确认",
        progress_current=1,
        progress_total=1,
        job_attempts=1,
        candidates=[
            ContentImportCandidateRecord(
                id=uuid.uuid4(),
                run_id=run_id,
                category=category,
                payload=payload,
                source_id=str(source_id),
                source_text="来自机器人蛋糕资料的原文证据",
                confidence=0.9,
                status="pending_review",
                version=1,
                created_at=now,
                updated_at=now,
            )
            for category, payload in categories
        ],
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )

    suggestions, profile = _fallback_synthesis_from_content_review(
        review,
        draft_rows=[
            {
                "import_item_id": source_id,
                "file_name": "机器人蛋糕资料.pdf",
                "document_id": uuid.uuid4(),
            }
        ],
        generation_version=3,
    )

    assert suggestions == []
    assert {item.field for item in profile} == {
        "products_services",
        "case_studies",
        "frequently_asked_questions",
    }
    assert all(item.sources[0].file_name == "机器人蛋糕资料.pdf" for item in profile)
    assert all(item.generation_version == 3 for item in profile)


def test_parse_merged_candidates_keeps_cross_source_contributions_and_warnings() -> None:
    first_source = uuid.uuid4()
    second_source = uuid.uuid4()
    parsed = _parse_merged_candidates(
        {
            "merged_candidates": [
                {
                    "category": "products",
                    "payload": {
                        "name": "机器人蛋糕协作系统",
                        "category": "智能制造",
                        "summary": "机器人制作蛋糕并协同工作",
                        "detail": "资料一提供材料能力，资料二补充协作机制",
                        "audience": "食品工厂",
                        "price_boundary": "",
                    },
                    "confidence": 0.86,
                    "source_ids": [str(first_source), str(second_source)],
                    "source_contributions": [
                        {"source_id": str(first_source), "contribution": "提供机器人躯体材料"},
                        {"source_id": str(second_source), "contribution": "补充共同协作机制"},
                    ],
                    "conflicts": ["材料名称存在不同表述"],
                    "missing_fields": ["价格边界"],
                }
            ]
        },
        source_rows={
            first_source: {"file_name": "材料说明.pdf"},
            second_source: {"file_name": "协作机制.pdf"},
        },
    )

    assert len(parsed) == 1
    assert parsed[0]["category"] == "products"
    assert parsed[0]["source_ids"] == [first_source, second_source]
    assert "材料说明.pdf：提供机器人躯体材料" in parsed[0]["source_text"]
    assert "协作机制.pdf：补充共同协作机制" in parsed[0]["source_text"]
    assert parsed[0]["field_warnings"] == [
        "存在跨资料冲突，请人工裁决",
        "待补字段：价格边界",
    ]


def test_fallback_merged_candidates_combines_same_enterprise_profile_sources() -> None:
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    source_ids = [uuid.uuid4(), uuid.uuid4()]
    review = ContentImportRunRecord(
        id=run_id,
        batch_id=uuid.uuid4(),
        status="review",
        provider="deepseek",
        model="flash",
        attempts=1,
        counts={"pending_review": 2},
        stage="completed",
        progress_current=2,
        progress_total=2,
        candidates=[
            ContentImportCandidateRecord(
                id=uuid.uuid4(),
                run_id=run_id,
                category="enterprise_profile",
                payload={
                    "company_name": "双维机器人蛋糕",
                    "summary": "机器人制作蛋糕",
                    "industry": "食品智能制造",
                    "region": "杭州",
                    "website": "",
                },
                source_id=str(source_id),
                source_text="原文",
                confidence=confidence,
                status="pending_review",
                version=1,
                created_at=now,
                updated_at=now,
            )
            for source_id, confidence in zip(source_ids, (0.9, 0.8), strict=True)
        ],
        created_at=now,
        updated_at=now,
    )

    merged = _fallback_merged_candidates(
        review,
        draft_rows=[
            {"import_item_id": source_ids[0], "file_name": "公司资料一.pdf"},
            {"import_item_id": source_ids[1], "file_name": "公司资料二.pdf"},
        ],
    )

    assert len(merged) == 1
    assert merged[0]["source_ids"] == source_ids
    assert "公司资料一.pdf" in merged[0]["source_text"]
    assert "公司资料二.pdf" in merged[0]["source_text"]


def test_merge_candidate_groups_combines_complementary_fields_and_sources() -> None:
    now = datetime.now(UTC)
    run_id = uuid.uuid4()
    first_source = uuid.uuid4()
    second_source = uuid.uuid4()
    candidates = {
        "c1": ContentImportCandidateRecord(
            id=uuid.uuid4(),
            run_id=run_id,
            category="products",
            payload={"name": "机器人蛋糕系统", "summary": "机器人制作蛋糕"},
            source_id=str(first_source),
            source_text="原文一",
            confidence=0.9,
            status="pending_review",
            version=1,
            created_at=now,
            updated_at=now,
        ),
        "c2": ContentImportCandidateRecord(
            id=uuid.uuid4(),
            run_id=run_id,
            category="products",
            payload={"name": "机器人蛋糕系统", "detail": "多机器人共同协作"},
            source_id=str(second_source),
            source_text="原文二",
            confidence=0.8,
            status="pending_review",
            version=1,
            created_at=now,
            updated_at=now,
        ),
    }

    merged = _merge_candidates_from_groups(
        {"groups": [{"category": "products", "candidate_ids": ["c1", "c2"]}]},
        candidate_lookup=candidates,
        source_rows={
            first_source: {"file_name": "产品资料.pdf"},
            second_source: {"file_name": "协作机制.pdf"},
        },
    )

    assert len(merged) == 1
    assert merged[0]["source_ids"] == [first_source, second_source]
    assert merged[0]["payload"]["summary"] == "机器人制作蛋糕"
    assert merged[0]["payload"]["detail"] == "多机器人共同协作"
    assert "产品资料.pdf" in merged[0]["source_text"]
    assert "协作机制.pdf" in merged[0]["source_text"]


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
        run_id = uuid.uuid4()
        batch_id = uuid.uuid4()
        content_review = ContentImportRunRecord(
            id=run_id,
            batch_id=batch_id,
            status="review",
            provider="integration",
            model="review-v1",
            attempts=1,
            counts={"accepted": 1, "pending_review": 1},
            candidates=[
                ContentImportCandidateRecord(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    category="products",
                    payload={"name": "Accepted product"},
                    source_id="source-accepted",
                    source_text="accepted evidence",
                    confidence=0.9,
                    status="accepted",
                    target_resource_type="product",
                    target_resource_id=uuid.uuid4(),
                    version=2,
                    created_at=now,
                    updated_at=now,
                ),
                ContentImportCandidateRecord(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    category="faqs",
                    payload={"question": "Pending?", "answer": "Pending."},
                    source_id="source-pending",
                    source_text="pending evidence",
                    confidence=0.8,
                    status="pending_review",
                    version=1,
                    created_at=now,
                    updated_at=now,
                ),
            ],
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        self.record = PlatformOnboardingSessionRecord(
            id=uuid.uuid4(),
            display_name="Acme·资料导入·2026-08-14·第 1 次",
            status="draft",
            tenant_slug="acme-demo",
            tenant_name="Acme",
            legal_name="Acme 法定名称",
            short_name="Acme",
            subject_type="association",
            admin_account="admin@acme.test",
            admin_display_name="Acme Admin",
            version=1,
            import_batch_ids=[batch_id],
            content_review=content_review,
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

    async def rename(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("rename", kwargs))
        return self.record.model_copy(
            update={
                "display_name": kwargs["display_name"],
                "version": kwargs["expected_version"] + 1,
            }
        )

    async def get_import_status(self, **kwargs: Any) -> PlatformOnboardingImportStatusRecord:
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

    async def attach_import_batch(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("attach", kwargs))
        return self.record.model_copy(update={"status": "processing", "version": 2})

    async def generate_suggestions(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("suggestions", kwargs))
        return self.record.model_copy(update={"status": "manual_required", "version": 2})

    async def synthesize_sources(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("synthesis", kwargs))
        return self.record.model_copy(
            update={
                "status": "review",
                "version": kwargs["expected_version"] + 2,
                "synthesis_status": "ready",
                "synthesis_version": 1,
            }
        )

    async def confirm(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("confirm", kwargs))
        return self.record.model_copy(update={"status": "confirmed", "version": 2})

    async def cancel(self, **kwargs: Any) -> PlatformOnboardingSessionRecord:
        self.calls.append(("cancel", kwargs))
        return self.record.model_copy(update={"status": "cancelled", "version": 2})

    async def regenerate_temporary_credential(
        self, **kwargs: Any
    ) -> PlatformOnboardingSessionRecord:
        self.calls.append(("credential.regenerate", kwargs))
        return self.record.model_copy(
            update={
                "status": "confirmed",
                "version": kwargs["expected_version"] + 1,
                "credential_delivery": TemporaryCredentialDelivery(
                    account="admin@acme.test",
                    temporary_password="Temporary-Only-123",  # noqa: S106
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                    shown_once=True,
                ),
            }
        )

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

    async def accept_content_candidate(self, **kwargs: Any) -> Any:
        self.calls.append(("candidate.accept", kwargs))
        return {
            "id": kwargs["candidate_id"],
            "run_id": uuid.uuid4(),
            "category": "products",
            "payload": {"name": "Accepted product"},
            "source_id": str(uuid.uuid4()),
            "source_text": "企业原文证据",
            "confidence": 0.9,
            "status": "accepted",
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
    monkeypatch.setattr(routes, "_admin_store", lambda _request: object())
    monkeypatch.setattr(routes, "_catalog_store", lambda _request: object())
    with TestClient(app) as client:
        yield client, service, import_store, principal_box


def test_route_surface_is_session_bound(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _, _ = route_client
    paths = client.app.openapi()["paths"]
    root = "/api/v1/platform/onboarding"
    assert set(paths[root]) == {"get", "post"}
    assert set(paths[f"{root}/{{onboarding_id}}"]) == {"get", "patch"}
    for suffix in ("suggestions", "synthesis", "confirm", "cancel"):
        assert set(paths[f"{root}/{{onboarding_id}}/{suffix}"]) == {"post"}
    assert set(paths[f"{root}/{{onboarding_id}}/imports"]) == {"get", "post"}
    assert set(paths[f"{root}/{{onboarding_id}}/candidates/{{candidate_id}}"]) == {"put"}
    assert set(paths[f"{root}/{{onboarding_id}}/candidates/{{candidate_id}}/accept"]) == {"post"}
    assert set(paths[f"{root}/{{onboarding_id}}/candidates/{{candidate_id}}/ignore"]) == {"post"}
    assert set(paths[f"{root}/{{onboarding_id}}/temporary-credential:regenerate"]) == {"post"}
    upload = paths[f"{root}/{{onboarding_id}}/imports"]["post"]
    serialized = str(upload)
    assert "tenant_id" not in serialized
    assert "company_id" not in serialized


def test_cross_source_synthesis_route_is_session_bound(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, _, _ = route_client
    response = client.post(
        f"/api/v1/platform/onboarding/{service.record.id}/synthesis",
        json={"expected_version": service.record.version},
    )

    assert response.status_code == 200
    assert response.json()["data"]["synthesis_status"] == "ready"
    assert service.calls[-1][0] == "synthesis"
    assert service.calls[-1][1]["onboarding_id"] == service.record.id


def test_accept_candidate_is_session_bound_and_forwards_review_fields(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, _, _ = route_client
    candidate_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/platform/onboarding/{service.record.id}/candidates/{candidate_id}/accept",
        json={"expected_version": 4, "apply_fields": ["name"]},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "accepted"
    call = next(payload for name, payload in service.calls if name == "candidate.accept")
    assert call["onboarding_id"] == service.record.id
    assert call["candidate_id"] == candidate_id
    assert call["expected_version"] == 4
    assert call["apply_fields"] == ["name"]


def test_import_progress_resolves_scope_from_session_only(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, _, _ = route_client
    response = client.get(f"/api/v1/platform/onboarding/{service.record.id}/imports")
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
    assert payload["legal_name"] == "Acme 法定名称"
    assert payload["short_name"] == "Acme"
    assert payload["content_review"]["counts"] == {
        "accepted": 1,
        "pending_review": 1,
    }
    assert [candidate["status"] for candidate in payload["content_review"]["candidates"]] == [
        "accepted",
        "pending_review",
    ]
    assert "admin_password" not in payload

    listed = client.get("/api/v1/platform/onboarding")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["content_review"]["id"] == payload["content_review"]["id"]


def test_start_rename_confirm_selection_and_credential_regeneration_contract(
    route_client: tuple[TestClient, RouteService, ImportStore, dict[str, StaffPrincipal]],
) -> None:
    client, service, _, _ = route_client
    started = client.post(
        "/api/v1/platform/onboarding",
        json={
            "display_name": "Acme 首批资料交接",
            "legal_name": "Acme 法定名称",
            "short_name": "Acme",
            "subject_type": "association",
            "admin_account": "admin@acme.test",
            "admin_display_name": "Acme Admin",
        },
    )
    assert started.status_code == 201
    start_body = next(payload for name, payload in service.calls if name == "start")["body"]
    assert start_body.display_name == "Acme 首批资料交接"

    renamed = client.patch(
        f"/api/v1/platform/onboarding/{service.record.id}",
        json={"expected_version": 1, "display_name": "Acme 第二版交接"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["display_name"] == "Acme 第二版交接"

    candidate_id = uuid.uuid4()
    confirmed = client.post(
        f"/api/v1/platform/onboarding/{service.record.id}/confirm",
        json={
            "expected_version": 1,
            "legal_name": "Acme 法定名称",
            "short_name": "Acme",
            "subject_type": "association",
            "candidate_selections": [
                {
                    "id": str(candidate_id),
                    "expected_version": 3,
                    "apply_fields": ["company_name"],
                }
            ],
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.headers["cache-control"] == "private, no-store"
    confirm_body = next(payload for name, payload in service.calls if name == "confirm")["body"]
    assert confirm_body.candidate_selections[0].id == candidate_id

    regenerated = client.post(
        f"/api/v1/platform/onboarding/{service.record.id}/temporary-credential:regenerate",
        json={"expected_version": 2},
    )
    assert regenerated.status_code == 200
    assert regenerated.headers["cache-control"] == "private, no-store"
    delivery = regenerated.json()["data"]["credential_delivery"]
    assert delivery["temporary_password"] == "Temporary-Only-123"  # noqa: S105
    assert delivery["shown_once"] is True


def test_default_onboarding_name_is_human_readable() -> None:
    assert (
        _default_onboarding_display_name(
            enterprise_name="星澜科技",
            created_at=datetime(2026, 8, 14, tzinfo=UTC),
            sequence_number=2,
        )
        == "星澜科技·资料导入·2026-08-14·第 2 次"
    )


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


def test_business_analysis_contract_covers_directions_and_cross_source_evidence() -> None:
    assert {
        "core_capabilities",
        "business_model",
        "business_directions",
        "evidence_conflicts",
        "missing_information",
    }.issubset(_BUSINESS_PROFILE_FIELDS)
    assert "同一企业资料" in _MERGED_CANDIDATE_SYSTEM_PROMPT
    assert "互相补充也应归为一组" in _MERGED_CANDIDATE_SYSTEM_PROMPT
    assert "每个输入 candidate_id 必须且只能出现一次" in _MERGED_CANDIDATE_SYSTEM_PROMPT
    assert "answer 字符串内禁止输出" in _MERGED_CANDIDATE_SYSTEM_PROMPT


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
        session,
        row,  # type: ignore[arg-type]
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
        ScalarSession(),
        row,  # type: ignore[arg-type]
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
    owner_predicate = "created_by = NULLIF(current_setting('app.user_id', true), '')::uuid"
    assert owner_predicate in migration
    assert "onboarding.created_by = " in migration
    assert "platform_onboarding_platform_only" in migration
    assert "platform_onboarding_imports_settled" in migration
    assert "platform_onboarding_drafts" in migration
    assert "SECURITY DEFINER" in migration


def test_handoff_migration_has_narrow_credential_and_retention_contract() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations/versions/20260814_0038_onboarding_content_handoff.py"
    ).read_text(encoding="utf-8")
    assert 'revision: str = "20260814_0038"' in migration
    assert 'down_revision: str | None = "20260813_0037"' in migration
    assert "staff_credentials_platform_onboarding_confirmed_update" in migration
    assert "onboarding.status = 'confirmed'" in migration
    assert "is_enabled AND must_change_password" in migration
    assert "platform_onboarding_content_reviews(p_session_ids uuid[])" in migration
    assert "WITH ORDINALITY AS bound_batch" in migration
    assert "onboarding.created_by = NULLIF" in migration
    assert "purge_expired_platform_onboarding_sessions" in migration
    assert "status IN ('cancelled','expired','failed')" in migration
    assert "confirmed_at IS NULL" in migration
    assert "expires_at <= pg_catalog.clock_timestamp()" in migration
    assert "RETURN expired_count + purged_count" in migration
    assert "audit_logs_retained" in migration
    assert "cf_ai_card_worker" in migration
