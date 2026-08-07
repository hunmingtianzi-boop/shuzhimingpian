from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.catalog_schemas import (
    EnterpriseTemplateDocument,
    EnterpriseTemplateRecord,
    ForbiddenTopicRecord,
    ManagedCardRecord,
    ProductRecord,
    PublicProductRecord,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError, api_error_handler
from app.api.routes import admin as admin_routes
from app.api.routes import public_catalog
from app.core.tokens import StaffPrincipal


class CatalogRouteStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.product = _product(version=7)
        self.card = _card(version=2)
        self.enterprise_template = EnterpriseTemplateRecord(
            card_id=self.card.id,
            version=self.card.version,
            draft=EnterpriseTemplateDocument(
                blocks=[
                    {
                        "id": "identity",
                        "type": "identity",
                        "sort_order": 0,
                        "title": "基础名片",
                    },
                    {
                        "id": "intro",
                        "type": "rich_text",
                        "sort_order": 1,
                        "body": "企业介绍",
                    },
                ]
            ),
        )
        self.topic = _topic(version=3, active=True)

    async def list_products(self, **kwargs: Any) -> tuple[list[ProductRecord], int]:
        self.calls.append(("list_products", kwargs))
        return [self.product], 1

    async def update_product(self, **kwargs: Any) -> ProductRecord:
        self.calls.append(("update_product", kwargs))
        self.product = self.product.model_copy(
            update={
                "name": kwargs["body"].name,
                "version": kwargs["expected_version"] + 1,
            }
        )
        return self.product

    async def get_product(self, **kwargs: Any) -> ProductRecord:
        self.calls.append(("get_product", kwargs))
        return self.product

    async def publish_product(self, **kwargs: Any) -> ProductRecord:
        self.calls.append(("publish_product", kwargs))
        self.product = self.product.model_copy(
            update={"status": "published", "version": kwargs["expected_version"] + 1}
        )
        return self.product

    async def list_cards(self, **kwargs: Any) -> tuple[list[ManagedCardRecord], int]:
        self.calls.append(("list_cards", kwargs))
        return [self.card], 1

    async def create_card(self, **kwargs: Any) -> ManagedCardRecord:
        self.calls.append(("create_card", kwargs))
        return self.card

    async def get_enterprise_template(self, **kwargs: Any) -> EnterpriseTemplateRecord:
        self.calls.append(("get_enterprise_template", kwargs))
        return self.enterprise_template

    async def update_enterprise_template(self, **kwargs: Any) -> EnterpriseTemplateRecord:
        self.calls.append(("update_enterprise_template", kwargs))
        self.enterprise_template = EnterpriseTemplateRecord(
            card_id=kwargs["card_id"],
            version=kwargs["expected_version"] + 1,
            draft=EnterpriseTemplateDocument.model_validate(kwargs["body"]),
        )
        return self.enterprise_template

    async def set_forbidden_topic_active(self, **kwargs: Any) -> ForbiddenTopicRecord:
        self.calls.append(("set_forbidden_topic_active", kwargs))
        self.topic = self.topic.model_copy(
            update={
                "is_active": kwargs["active"],
                "version": kwargs["expected_version"] + 1,
            }
        )
        return self.topic

    async def list_public_products(self, **kwargs: Any) -> tuple[list[PublicProductRecord], int]:
        self.calls.append(("list_public_products", kwargs))
        return [
            PublicProductRecord(
                slug=self.product.slug,
                name=self.product.name,
                category=self.product.category,
                summary=self.product.summary,
                detail=self.product.detail,
                audience=self.product.audience,
                price_boundary=self.product.price_boundary,
                image_url=self.product.image_url,
                sort_order=self.product.sort_order,
                published_at=datetime.now(UTC),
            )
        ], 1


class CatalogKnowledgeRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def sync_product(self, **kwargs: Any) -> uuid.UUID:
        self.calls.append(kwargs)
        return uuid.uuid4()


@pytest.fixture
def catalog_client() -> tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]]:
    store = CatalogRouteStore()
    knowledge = CatalogKnowledgeRecorder()
    principal_box = {"value": _principal(role="company_admin")}
    app = FastAPI()
    app.state.catalog_store = store
    app.state.catalog_knowledge_synchronizer = knowledge
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(admin_routes.router, prefix="/api/v1")
    app.include_router(public_catalog.router, prefix="/api/v1")
    app.dependency_overrides[get_staff_principal] = lambda: principal_box["value"]
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


def _product(*, version: int) -> ProductRecord:
    now = datetime.now(UTC)
    return ProductRecord(
        id=uuid.uuid4(),
        slug="enterprise-ai",
        name="企业 AI 助手",
        category="AI",
        summary="可追溯的企业问答",
        detail="企业级知识检索与问答服务",
        audience="企业客户",
        price_boundary="按项目报价",
        visibility="public",
        sort_order=10,
        settings={"badge": "featured"},
        status="draft",
        version=version,
        created_at=now,
        updated_at=now,
    )


def _card(*, version: int) -> ManagedCardRecord:
    now = datetime.now(UTC)
    slug = "c-" + "a" * 36
    share_url = f"https://cards.example.com/c/{slug}"
    return ManagedCardRecord(
        id=uuid.uuid4(),
        card_kind="employee",
        owner_user_id=uuid.uuid4(),
        slug=slug,
        display_name="张三的名片",
        title="企业解决方案顾问",
        assistant_name="小创",
        suggested_questions=["你们能解决什么问题？"],
        policy_versions={
            "privacy": "privacy-v1",
            "profile_personalization": "profile-personalization-v1",
        },
        status="draft",
        version=version,
        share_url=share_url,
        qr_url=share_url,
        created_at=now,
        updated_at=now,
    )


def _topic(*, version: int, active: bool) -> ForbiddenTopicRecord:
    now = datetime.now(UTC)
    return ForbiddenTopicRecord(
        id=uuid.uuid4(),
        topic="竞争对手贬损",
        match_terms=["贬低对手"],
        action="refuse",
        is_active=active,
        version=version,
        created_at=now,
        updated_at=now,
    )


def _product_payload(*, name: str = "更新后的产品") -> dict[str, Any]:
    return {
        "slug": "enterprise-ai",
        "name": name,
        "category": "AI",
        "summary": "可追溯的企业问答",
        "detail": "企业级知识检索与问答服务",
        "audience": "企业客户",
        "price_boundary": "按项目报价",
        "visibility": "public",
        "sort_order": 10,
        "settings": {"badge": "featured"},
    }


def test_product_update_forwards_if_match_and_returns_new_etag(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = catalog_client

    response = client.put(
        f"/api/v1/admin/products/{store.product.id}",
        headers={"If-Match": 'W/"7"'},
        json=_product_payload(),
    )

    assert response.status_code == 200
    assert response.headers["etag"] == '"8"'
    assert response.json()["data"]["name"] == "更新后的产品"
    call = store.calls[-1]
    assert call[0] == "update_product"
    assert call[1]["expected_version"] == 7


def test_product_publish_indexes_the_exact_draft_before_publication(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = catalog_client
    knowledge = client.app.state.catalog_knowledge_synchronizer

    response = client.post(
        f"/api/v1/admin/products/{store.product.id}:publish",
        headers={"If-Match": '"7"'},
    )

    assert response.status_code == 200
    assert [name for name, _ in store.calls[-2:]] == ["get_product", "publish_product"]
    assert len(knowledge.calls) == 1
    assert knowledge.calls[0]["product"].version == 7
    assert knowledge.calls[0]["scope"].company_id == principal_box["value"].company_id
    assert response.json()["data"]["status"] == "published"


def test_product_publish_rejects_a_stale_version_before_indexing(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = catalog_client
    knowledge = client.app.state.catalog_knowledge_synchronizer

    response = client.post(
        f"/api/v1/admin/products/{store.product.id}:publish",
        headers={"If-Match": '"6"'},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERSION_CONFLICT"
    assert knowledge.calls == []
    assert [name for name, _ in store.calls] == ["get_product"]


def test_card_owner_needs_explicit_catalog_permission(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = catalog_client
    principal_box["value"] = _principal(role="card_owner")

    response = client.get("/api/v1/admin/products")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert store.calls == []


def test_card_owner_scope_is_forwarded_after_permission_check(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, principal_box = catalog_client
    principal_box["value"] = _principal(role="card_owner", permissions=("card.read",))

    response = client.get("/api/v1/admin/cards?limit=10&offset=0")

    assert response.status_code == 200
    call = store.calls[-1]
    assert call[0] == "list_cards"
    assert call[1]["scope"].role == "card_owner"
    assert call[1]["scope"].actor_user_id == principal_box["value"].user_id


def test_multicard_create_does_not_accept_a_client_selected_slug(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = catalog_client

    rejected = client.post(
        "/api/v1/admin/cards",
        json={
            "slug": "guessable-slug",
            "display_name": "销售名片",
            "title": "销售顾问",
        },
    )
    accepted = client.post(
        "/api/v1/admin/cards",
        json={"display_name": "销售名片", "title": "销售顾问"},
    )

    assert rejected.status_code == 422
    assert accepted.status_code == 201
    assert accepted.headers["etag"] == '"2"'
    assert accepted.json()["data"]["slug"] == store.card.slug
    assert accepted.json()["data"]["qr_url"] == accepted.json()["data"]["share_url"]


def test_enterprise_template_routes_read_draft_and_forward_if_match(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = catalog_client

    read_response = client.get(f"/api/v1/admin/cards/{store.card.id}/enterprise-template")
    update_response = client.put(
        f"/api/v1/admin/cards/{store.card.id}/enterprise-template",
        headers={"If-Match": 'W/"2"'},
        json={
            "schema_version": 1,
            "theme_key": "warm",
            "blocks": [
                {
                    "id": "identity",
                    "type": "identity",
                    "sort_order": 0,
                    "title": "基础名片",
                    "directory_enabled": True,
                },
                {
                    "id": "cta",
                    "type": "cta",
                    "sort_order": 1,
                    "title": "联系我们",
                    "cta_label": "立即沟通",
                    "cta_url": "https://example.test/contact",
                },
            ],
        },
    )

    assert read_response.status_code == 200
    assert [block["id"] for block in read_response.json()["data"]["draft"]["blocks"]] == [
        "identity",
        "intro",
    ]
    assert update_response.status_code == 200
    assert update_response.headers["etag"] == '"3"'
    assert update_response.json()["data"]["draft"]["theme_key"] == "warm"
    assert [name for name, _ in store.calls[-2:]] == [
        "get_enterprise_template",
        "update_enterprise_template",
    ]
    assert store.calls[-1][1]["expected_version"] == 2


def test_forbidden_topic_deactivation_requires_and_forwards_if_match(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = catalog_client

    response = client.post(
        f"/api/v1/admin/forbidden-topics/{store.topic.id}/deactivate",
        headers={"If-Match": '"3"'},
    )

    assert response.status_code == 200
    assert response.headers["etag"] == '"4"'
    assert response.json()["data"]["is_active"] is False
    call = store.calls[-1]
    assert call[0] == "set_forbidden_topic_active"
    assert call[1]["expected_version"] == 3
    assert call[1]["active"] is False


def test_public_product_route_is_card_scoped_and_paginated(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, store, _ = catalog_client
    card_slug = "c-" + "f" * 36

    response = client.get(f"/api/v1/public/cards/{card_slug}/products?limit=5&offset=10")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["limit"] == 5
    assert response.json()["offset"] == 10
    assert "settings" not in response.json()["data"][0]
    assert "version" not in response.json()["data"][0]
    call = store.calls[-1]
    assert call == (
        "list_public_products",
        {"card_slug": card_slug, "limit": 5, "offset": 10},
    )


def test_frozen_v1_catalog_route_aliases_are_registered(
    catalog_client: tuple[TestClient, CatalogRouteStore, dict[str, StaffPrincipal]],
) -> None:
    client, _, _ = catalog_client
    paths = client.app.openapi()["paths"]

    expected_methods = {
        "/api/v1/admin/products/{product_id}": {"patch"},
        "/api/v1/admin/products/{product_id}:publish": {"post"},
        "/api/v1/admin/cases": {"get", "post"},
        "/api/v1/admin/cases/{case_study_id}": {"get", "patch", "delete"},
        "/api/v1/admin/cases/{case_study_id}:publish": {"post"},
        "/api/v1/admin/forbidden-topics/{topic_id}": {"patch"},
        "/api/v1/admin/cards/{card_id}": {"patch"},
        "/api/v1/admin/cards/{card_id}:publish": {"post"},
        "/api/v1/admin/cards/{card_id}:deactivate": {"post"},
        "/api/v1/public/cards/{slug}/cases": {"get"},
        "/api/v1/public/cards/{slug}/cases/{id}": {"get"},
    }
    for path, methods in expected_methods.items():
        assert path in paths
        assert methods.issubset(paths[path])
