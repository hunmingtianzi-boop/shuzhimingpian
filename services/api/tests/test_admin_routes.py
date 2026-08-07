from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin_schemas import (
    CardProfile,
    CompanyProfile,
    KnowledgeDocumentDetail,
    KnowledgeDocumentRecord,
    KnowledgeDraftResult,
    KnowledgePublishResult,
    KnowledgeVersionSummary,
    SelectableFaqRecord,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import admin as admin_routes
from app.core.tokens import StaffPrincipal


class RouteStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.company = _company_profile(version=7)
        self.card = _card_profile(version=4)
        self.document, self.draft, self.published = _knowledge_records()
        self.detail = KnowledgeDocumentDetail(
            **self.document.model_dump(),
            raw_text="完整的企业知识正文",
            visibility="public",
            metadata={"source_url": "https://example.com/docs"},
            editable_version_id=self.draft.draft_version.id,
        )

    async def get_company_profile(self, **kwargs: Any) -> CompanyProfile:
        self.calls.append(("get_company", kwargs))
        return self.company

    async def update_company_profile(self, **kwargs: Any) -> CompanyProfile:
        self.calls.append(("update_company", kwargs))
        self.company = self.company.model_copy(
            update={"name": kwargs["body"].name, "version": kwargs["expected_version"] + 1}
        )
        return self.company

    async def get_card(self, **kwargs: Any) -> CardProfile:
        self.calls.append(("get_card", kwargs))
        return self.card

    async def update_card(self, **kwargs: Any) -> CardProfile:
        self.calls.append(("update_card", kwargs))
        self.card = self.card.model_copy(
            update={
                "display_name": kwargs["body"].display_name,
                "version": kwargs["expected_version"] + 1,
            }
        )
        return self.card

    async def complete_enterprise_setup(
        self, **kwargs: Any
    ) -> tuple[CompanyProfile, CardProfile]:
        self.calls.append(("complete_setup", kwargs))
        self.company = self.company.model_copy(
            update={"onboarding_status": "completed", "version": self.company.version + 1}
        )
        self.card = self.card.model_copy(
            update={
                "onboarding_status": "completed",
                "status": "published",
                "published_at": datetime.now(UTC),
                "version": self.card.version + 1,
            }
        )
        return self.company, self.card

    async def list_documents(
        self, **kwargs: Any
    ) -> tuple[list[SelectableFaqRecord | KnowledgeDocumentRecord], int]:
        self.calls.append(("list_documents", kwargs))
        if kwargs.get("selectable_faq"):
            return [
                SelectableFaqRecord.model_validate(
                    {
                        **self.document.model_dump(),
                        "visibility": "public",
                        "answer": "公开 FAQ 答案",
                    }
                )
            ], 1
        return [self.document], 1

    async def create_document(self, **kwargs: Any) -> KnowledgeDocumentRecord:
        self.calls.append(("create_document", kwargs))
        return self.document

    async def get_document_detail(self, **kwargs: Any) -> KnowledgeDocumentDetail:
        self.calls.append(("get_document_detail", kwargs))
        return self.detail

    async def put_document_draft(self, **kwargs: Any) -> KnowledgeDraftResult:
        self.calls.append(("put_draft", kwargs))
        return self.draft

    async def publish_document(self, **kwargs: Any) -> KnowledgePublishResult:
        self.calls.append(("publish", kwargs))
        return self.published


@pytest.fixture
def route_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RouteStore, dict[str, StaffPrincipal]]:
    store = RouteStore()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(admin_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
    monkeypatch.setattr(admin_routes, "_store", lambda _request: store)
    with TestClient(app) as client:
        yield client, store, principal_box


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


def _company_profile(*, version: int) -> CompanyProfile:
    return CompanyProfile(
        id=uuid.uuid4(),
        name="示例企业",
        summary="企业简介",
        industry="软件",
        region="杭州",
        website="https://example.com",
        profile_personalization_policy_version="profile-personalization-v1",
        onboarding_status="content_pending",
        status="active",
        version=version,
        updated_at=datetime.now(UTC),
    )


def _card_profile(*, version: int) -> CardProfile:
    return CardProfile(
        id=uuid.uuid4(),
        card_kind="employee",
        owner_user_id=uuid.uuid4(),
        slug="example-card",
        display_name="示例名片",
        title="企业顾问",
        suggested_questions=["你们提供什么服务？"],
        policy_versions={"privacy": "privacy-v1"},
        status="draft",
        onboarding_status="content_pending",
        version=version,
        updated_at=datetime.now(UTC),
    )


def _knowledge_records() -> tuple[
    KnowledgeDocumentRecord, KnowledgeDraftResult, KnowledgePublishResult
]:
    now = datetime.now(UTC)
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    draft_version = KnowledgeVersionSummary(
        id=version_id,
        version_number=1,
        review_status="draft",
        chunk_count=1,
        indexed_chunk_count=0,
        created_at=now,
    )
    document = KnowledgeDocumentRecord(
        id=document_id,
        source_type="manual",
        source_id=f"admin:{document_id}",
        title="产品知识",
        status="draft",
        version=2,
        latest_version=draft_version,
        created_at=now,
        updated_at=now,
    )
    approved_version = draft_version.model_copy(
        update={
            "review_status": "approved",
            "indexed_chunk_count": 1,
            "published_at": now,
        }
    )
    published_document = document.model_copy(
        update={
            "status": "published",
            "version": 3,
            "current_version_id": version_id,
            "current_version_number": 1,
            "latest_version": approved_version,
        }
    )
    return (
        document,
        KnowledgeDraftResult(document=document, draft_version=draft_version),
        KnowledgePublishResult(
            document=published_document,
            published_version=approved_version,
            index_job_id=uuid.uuid4(),
            index_status="succeeded",
        ),
    )


def test_admin_router_exposes_requested_vertical_slice(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _ = route_client
    paths = client.app.openapi()["paths"]

    assert set(paths["/api/v1/admin/company/profile"]) == {"get", "put"}
    assert set(paths["/api/v1/admin/card"]) == {"get", "put"}
    assert set(paths["/api/v1/admin/setup/complete"]) == {"post"}
    assert set(paths["/api/v1/admin/knowledge/documents"]) == {"get", "post"}
    assert set(paths["/api/v1/admin/knowledge/documents/{document_id}"]) == {"get", "put"}
    assert "post" in paths["/api/v1/admin/knowledge/documents/{document_id}/publish"]


def test_company_profile_uses_etag_and_if_match_version(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    get_response = client.get("/api/v1/admin/company/profile")
    put_response = client.put(
        "/api/v1/admin/company/profile",
        headers={"If-Match": 'W/"7"'},
        json={
            "name": "更新后的企业",
            "summary": "更新后的简介",
            "industry": "制造业",
            "region": "上海",
            "website": "https://example.org",
            "logo_url": "/api/v1/public/card-assets/company/logo.webp",
            "profile_personalization_policy_version": "profile-personalization-v2",
        },
    )

    assert get_response.status_code == 200
    assert get_response.headers["etag"] == '"7"'
    assert put_response.status_code == 200
    assert put_response.headers["etag"] == '"8"'
    assert put_response.json()["data"]["name"] == "更新后的企业"
    update_call = next(payload for name, payload in store.calls if name == "update_company")
    assert update_call["expected_version"] == 7
    assert update_call["body"].logo_url == (
        "/api/v1/public/card-assets/company/logo.webp"
    )


def test_card_uses_etag_and_if_match_version(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    get_response = client.get("/api/v1/admin/card")
    put_response = client.put(
        "/api/v1/admin/card",
        headers={"If-Match": '"4"'},
        json={
            "slug": "updated-card",
            "display_name": "更新后的名片",
            "title": "解决方案顾问",
            "avatar_url": "/api/v1/public/card-assets/company/avatar.webp",
            "assistant_name": "企业助手",
            "welcome_message": "欢迎咨询",
            "suggested_questions": ["你们提供什么服务？"],
            "policy_versions": {
                "privacy": "privacy-v2",
                "profile_personalization": "profile-personalization-v2",
            },
        },
    )

    assert get_response.status_code == 200
    assert get_response.headers["etag"] == '"4"'
    assert put_response.status_code == 200
    assert put_response.headers["etag"] == '"5"'
    update_call = next(payload for name, payload in store.calls if name == "update_card")
    assert update_call["expected_version"] == 4
    assert update_call["body"].avatar_url == (
        "/api/v1/public/card-assets/company/avatar.webp"
    )


def test_admin_asset_urls_reject_unsafe_remote_destinations(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _ = route_client

    response = client.put(
        "/api/v1/admin/card",
        headers={"If-Match": '"4"'},
        json={
            "slug": "updated-card",
            "display_name": "更新后的名片",
            "title": "解决方案顾问",
            "avatar_url": "http://127.0.0.1/private.webp",
            "assistant_name": "企业助手",
            "welcome_message": "欢迎咨询",
            "suggested_questions": [],
            "policy_versions": {},
        },
    )

    assert response.status_code == 422


def test_company_admin_can_complete_enterprise_setup(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = route_client

    response = client.post("/api/v1/admin/setup/complete", json={})

    assert response.status_code == 200
    assert response.json()["data"]["completed"] is True
    assert response.json()["data"]["company"]["onboarding_status"] == "completed"
    assert response.json()["data"]["card"]["onboarding_status"] == "completed"
    assert response.json()["data"]["card"]["status"] == "published"
    assert any(name == "complete_setup" for name, _payload in store.calls)


@pytest.mark.parametrize("value", ["", "0", 'W/"abc"', '"1.5"'])
def test_invalid_if_match_is_rejected(value: str) -> None:
    with pytest.raises(ApiError) as captured:
        admin_routes.parse_if_match(value)
    assert captured.value.code == "INVALID_IF_MATCH"


def test_non_admin_needs_explicit_permission(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, principal_box = route_client
    principal_box["value"] = _principal(role="card_owner")

    forbidden = client.get("/api/v1/admin/company/profile")

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    principal_box["value"] = _principal(
        role="card_owner",
        permissions=("company.profile.read",),
    )
    allowed = client.get("/api/v1/admin/company/profile")
    assert allowed.status_code == 200


def test_knowledge_review_permission_covers_create_draft_list_and_publish(
    route_client: tuple[TestClient, RouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = route_client
    principal_box["value"] = _principal(
        role="card_owner",
        permissions=("knowledge.review",),
    )
    document_id = store.document.id
    version_id = store.draft.draft_version.id

    list_response = client.get("/api/v1/admin/knowledge/documents?limit=10")
    selectable_response = client.get(
        "/api/v1/admin/knowledge/documents?limit=10&selectable_faq=true"
    )
    detail_response = client.get(f"/api/v1/admin/knowledge/documents/{document_id}")
    create_response = client.post(
        "/api/v1/admin/knowledge/documents",
        json={"title": "产品知识", "source_type": "manual"},
    )
    draft_response = client.put(
        f"/api/v1/admin/knowledge/documents/{document_id}",
        json={
            "title": "产品知识",
            "raw_text": "这是仅在发布成功后才会生效的新知识。",
            "visibility": "public",
            "metadata": {"source_url": "https://example.com/docs"},
        },
    )
    publish_response = client.post(
        f"/api/v1/admin/knowledge/documents/{document_id}/publish",
        json={"version_id": str(version_id)},
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    assert selectable_response.status_code == 200
    assert selectable_response.json()["data"][0]["visibility"] == "public"
    assert selectable_response.json()["data"][0]["answer"] == "公开 FAQ 答案"
    list_calls = [payload for name, payload in store.calls if name == "list_documents"]
    assert list_calls[-1]["selectable_faq"] is True
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["raw_text"] == "完整的企业知识正文"
    assert create_response.status_code == 201
    assert draft_response.status_code == 200
    assert draft_response.json()["data"]["draft_version"]["review_status"] == "draft"
    assert publish_response.status_code == 200
    assert publish_response.json()["data"]["index_status"] == "succeeded"
    publish_call = next(payload for name, payload in store.calls if name == "publish")
    assert publish_call["version_id"] == version_id
