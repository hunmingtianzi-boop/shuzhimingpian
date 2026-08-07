from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.api.catalog_schemas import CreateCardRequest, ManagedCardRecord, validate_safe_asset_url
from app.api.errors import ApiError
from app.db.models import Card, ContentStatus, Product, Visibility
from app.services import catalog_store as catalog_module
from app.services.catalog_store import (
    CatalogScope,
    CatalogStore,
    company_scope_filters,
    generate_card_slug,
    is_public_content,
    managed_card_filters,
    public_content_filters,
    require_version,
)


def _scope(*, role: str = "company_admin") -> CatalogScope:
    return CatalogScope(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        role=role,
    )


def _compiled(statement: Any) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_company_queries_pin_tenant_and_company_even_with_rls() -> None:
    scope = _scope()
    sql = _compiled(select(Product.id).where(*company_scope_filters(Product, scope)))

    assert "products.tenant_id" in sql
    assert str(scope.tenant_id) in sql
    assert "products.company_id" in sql
    assert str(scope.company_id) in sql


def test_card_owner_query_adds_owner_filter_but_admin_query_does_not() -> None:
    owner_scope = _scope(role="card_owner")
    admin_scope = CatalogScope(
        tenant_id=owner_scope.tenant_id,
        company_id=owner_scope.company_id,
        actor_user_id=owner_scope.actor_user_id,
        role="company_admin",
    )

    owner_sql = _compiled(select(Card.id).where(*managed_card_filters(owner_scope)))
    admin_sql = _compiled(select(Card.id).where(*managed_card_filters(admin_scope)))

    assert "cards.owner_user_id" in owner_sql
    assert str(owner_scope.actor_user_id) in owner_sql
    assert "cards.owner_user_id" not in admin_sql
    assert "cards.deleted_at IS NULL" in owner_sql


def test_public_query_requires_published_public_non_deleted_content() -> None:
    scope = _scope()
    sql = _compiled(
        select(Product.id).where(
            *public_content_filters(
                Product,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
        )
    )

    assert "products.deleted_at IS NULL" in sql
    assert "products.status = 'published'" in sql
    assert "products.visibility = 'public'" in sql
    assert "products.published_at IS NOT NULL" in sql
    assert "products.published_at <= now()" in sql
    assert str(scope.tenant_id) in sql
    assert str(scope.company_id) in sql


def test_stale_if_match_version_is_rejected_with_current_version() -> None:
    with pytest.raises(ApiError) as captured:
        require_version(8, 7)

    assert captured.value.status_code == 409
    assert captured.value.code == "VERSION_CONFLICT"
    assert captured.value.details == {"current_version": 8}


def test_card_slugs_are_unique_in_sample_and_have_144_bits_of_entropy() -> None:
    slugs = {generate_card_slug() for _ in range(512)}

    assert len(slugs) == 512
    assert all(re.fullmatch(r"c-[0-9a-f]{36}", slug) for slug in slugs)


def test_remote_http_public_card_base_requires_explicit_opt_in() -> None:
    public_base = "http://47.83.235.176"

    with pytest.raises(ValueError, match="must use HTTPS"):
        catalog_module._normalize_public_base_url(public_base)

    assert (
        catalog_module._normalize_public_base_url(
            public_base,
            allow_insecure_http=True,
        )
        == public_base
    )


class _ConstraintDiag:
    constraint_name = "uq_cards_slug"


class _ConstraintError(Exception):
    diag = _ConstraintDiag()


class CollisionHarness(CatalogStore):
    def __init__(self, slugs: list[str]) -> None:
        iterator = iter(slugs)
        super().__init__(
            cast(Any, object()),
            slug_factory=lambda: next(iterator),
        )
        self.attempts: list[str] = []

    async def _create_card_attempt(self, **kwargs: Any) -> ManagedCardRecord:
        slug = cast(str, kwargs["slug"])
        self.attempts.append(slug)
        if len(self.attempts) == 1:
            raise IntegrityError("INSERT", {}, _ConstraintError("collision"))
        body = cast(CreateCardRequest, kwargs["body"])
        owner_user_id = cast(uuid.UUID | None, kwargs["owner_user_id"])
        now = datetime.now(UTC)
        share_url = f"http://127.0.0.1:4173/c/{slug}"
        return ManagedCardRecord(
            id=uuid.uuid4(),
            card_kind=body.card_kind,
            owner_user_id=owner_user_id,
            slug=slug,
            display_name=body.display_name,
            title=body.title,
            suggested_questions=body.suggested_questions,
            policy_versions=body.policy_versions,
            status="draft",
            version=1,
            share_url=share_url,
            qr_url=share_url,
            created_at=now,
            updated_at=now,
        )


async def test_card_creation_retries_a_slug_collision_in_a_fresh_attempt() -> None:
    first = "c-" + "a" * 36
    second = "c-" + "b" * 36
    store = CollisionHarness([first, second])
    scope = _scope()

    result = await store.create_card(
        scope=scope,
        body=CreateCardRequest(
            owner_user_id=scope.actor_user_id,
            display_name="销售名片",
            title="解决方案顾问",
        ),
    )

    assert store.attempts == [first, second]
    assert result.slug == second
    assert result.qr_url == result.share_url


async def test_card_owner_cannot_create_a_card_for_another_user() -> None:
    store = CollisionHarness(["c-" + "a" * 36])
    scope = _scope(role="card_owner")

    with pytest.raises(ApiError) as captured:
        await store.create_card(
            scope=scope,
            body=CreateCardRequest(
                owner_user_id=uuid.uuid4(),
                display_name="越权名片",
                title="不应创建",
            ),
        )

    assert captured.value.status_code == 403
    assert store.attempts == []


async def test_company_admin_can_create_employee_independent_enterprise_card() -> None:
    store = CollisionHarness(["c-" + "a" * 36, "c-" + "b" * 36])

    result = await store.create_card(
        scope=_scope(),
        body=CreateCardRequest(
            card_kind="enterprise",
            display_name="示例企业官方名片",
            title="企业官方主页",
        ),
    )

    assert result.card_kind == "enterprise"
    assert result.owner_user_id is None


async def test_card_owner_cannot_create_enterprise_official_card() -> None:
    store = CollisionHarness(["c-" + "a" * 36])

    with pytest.raises(ApiError) as captured:
        await store.create_card(
            scope=_scope(role="card_owner"),
            body=CreateCardRequest(
                card_kind="enterprise",
                display_name="越权企业名片",
                title="不应创建",
            ),
        )

    assert captured.value.status_code == 403
    assert store.attempts == []


def test_archive_makes_published_content_ineligible_immediately() -> None:
    now = datetime.now(UTC)
    product = Product(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        slug="published-product",
        name="产品",
        summary="简介",
        detail="详情",
        visibility=Visibility.PUBLIC,
        status=ContentStatus.PUBLISHED,
        published_at=now - timedelta(minutes=1),
        sort_order=0,
        settings={},
        version=4,
    )

    assert is_public_content(
        status=product.status,
        visibility=product.visibility,
        published_at=product.published_at,
        deleted_at=product.deleted_at,
        now=now,
    )

    catalog_module._archive_resource(product, label="产品")

    assert product.status == ContentStatus.ARCHIVED
    assert product.version == 5
    assert not is_public_content(
        status=product.status,
        visibility=product.visibility,
        published_at=product.published_at,
        deleted_at=product.deleted_at,
        now=now,
    )


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "javascript:alert(1)",
        "http://example.com/image.png",
        "https://127.0.0.1/image.png",
        "https://user:password@example.com/image.png",
        "//evil.example/image.png",
    ],
)
def test_asset_url_allowlist_rejects_unsafe_destinations(unsafe_url: str) -> None:
    with pytest.raises(ValueError):
        validate_safe_asset_url(unsafe_url)


def test_asset_url_allowlist_accepts_first_party_and_public_https() -> None:
    assert validate_safe_asset_url("/assets/product.png") == "/assets/product.png"
    assert (
        validate_safe_asset_url("https://cdn.example.com/product.png")
        == "https://cdn.example.com/product.png"
    )


async def test_set_scope_passes_exact_tenant_and_company_to_rls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, uuid.UUID, uuid.UUID]] = []

    async def fake_set_rls_context(
        session: object,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        calls.append((session, tenant_id, company_id))

    monkeypatch.setattr(catalog_module, "set_rls_context", fake_set_rls_context)
    scope = _scope()
    session = object()
    store = CatalogStore(cast(Any, object()))

    await store._set_scope(cast(Any, session), scope)

    assert calls == [(session, scope.tenant_id, scope.company_id)]
