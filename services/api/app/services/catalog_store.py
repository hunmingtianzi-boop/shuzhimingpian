from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.catalog_schemas import (
    CardComposerDefaultRecord,
    CaseStudyRecord,
    CreateCardRequest,
    CreateCaseStudyRequest,
    CreateForbiddenTopicRequest,
    CreateProductRequest,
    EnterpriseTemplateDocument,
    EnterpriseTemplateRecord,
    ForbiddenTopicRecord,
    ManagedCardRecord,
    ProductRecord,
    PublicCaseStudyRecord,
    PublicProductRecord,
    UpdateCaseStudyRequest,
    UpdateEnterpriseTemplateRequest,
    UpdateForbiddenTopicRequest,
    UpdateManagedCardRequest,
    UpdateProductRequest,
    validate_safe_asset_url,
)
from app.api.errors import ApiError
from app.db.models import (
    Card,
    CardContactField,
    CardKind,
    CaseStudy,
    Company,
    ContentStatus,
    ForbiddenTopic,
    KnowledgeChunk,
    KnowledgeDocument,
    LifecycleStatus,
    Membership,
    Product,
    User,
    Visibility,
    WeComCardContactWay,
)
from app.db.session import resolve_public_card_scope, set_rls_context
from app.services.audit import append_audit
from app.services.enterprise_content_store import effective_overrides

_CARD_SLUG_ATTEMPTS = 8


@dataclass(frozen=True, slots=True)
class CatalogScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    role: str

    @property
    def is_card_owner(self) -> bool:
        return self.role == "card_owner"


@dataclass(frozen=True, slots=True)
class EmployeeIdentityProjection:
    display_name: str
    job_title: str | None
    avatar_url: str | None
    business_summary: str | None


@dataclass(frozen=True, slots=True)
class ForbiddenTopicRule:
    id: uuid.UUID
    topic: str
    match_terms: tuple[str, ...]
    action: str
    safe_response: str | None
    version: int


def generate_card_slug() -> str:
    """Return a URL-safe card slug with 144 bits of cryptographic entropy."""

    return f"c-{secrets.token_hex(18)}"


def require_version(current: int, expected: int) -> None:
    if current != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "资源已被其他操作更新，请刷新后重试",
            details={"current_version": current},
        )


def company_scope_filters(model: Any, scope: CatalogScope) -> tuple[Any, ...]:
    return (
        model.tenant_id == scope.tenant_id,
        model.company_id == scope.company_id,
    )


def managed_card_filters(scope: CatalogScope) -> tuple[Any, ...]:
    filters: list[Any] = [
        Card.tenant_id == scope.tenant_id,
        Card.company_id == scope.company_id,
        Card.deleted_at.is_(None),
    ]
    if scope.is_card_owner:
        filters.extend(
            (
                Card.card_kind == CardKind.EMPLOYEE,
                Card.owner_user_id == scope.actor_user_id,
            )
        )
    return tuple(filters)


def public_content_filters(
    model: Any,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
) -> tuple[Any, ...]:
    return (
        model.tenant_id == tenant_id,
        model.company_id == company_id,
        model.deleted_at.is_(None),
        model.status == ContentStatus.PUBLISHED,
        model.visibility == Visibility.PUBLIC,
        model.published_at.is_not(None),
        model.published_at <= func.now(),
    )


def eligible_faq_document_statement(
    scope: CatalogScope,
    document_ids: set[uuid.UUID],
) -> Any:
    """Select selectable FAQ ids while pinning every tenant/public boundary."""

    return (
        select(KnowledgeDocument.id)
        .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeDocument.id.in_(document_ids),
            KnowledgeDocument.tenant_id == scope.tenant_id,
            KnowledgeDocument.company_id == scope.company_id,
            KnowledgeDocument.source_type == "faq",
            KnowledgeDocument.status == ContentStatus.PUBLISHED,
            KnowledgeDocument.current_version_id.is_not(None),
            KnowledgeChunk.tenant_id == scope.tenant_id,
            KnowledgeChunk.company_id == scope.company_id,
            KnowledgeChunk.version_id == KnowledgeDocument.current_version_id,
            KnowledgeChunk.is_active.is_(True),
            KnowledgeChunk.visibility == Visibility.PUBLIC,
        )
        .distinct()
    )


def is_public_content(
    *,
    status: ContentStatus,
    visibility: Visibility,
    published_at: datetime | None,
    deleted_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    current = now or datetime.now(UTC)
    return (
        deleted_at is None
        and status == ContentStatus.PUBLISHED
        and visibility == Visibility.PUBLIC
        and published_at is not None
        and published_at <= current
    )


class CatalogStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        public_card_base_url: str = "http://127.0.0.1:4173",
        allow_insecure_http: bool = False,
        slug_factory: Callable[[], str] = generate_card_slug,
    ) -> None:
        self._sessions = session_factory
        self._public_card_base_url = _normalize_public_base_url(
            public_card_base_url,
            allow_insecure_http=allow_insecure_http,
        )
        self._slug_factory = slug_factory

    async def list_products(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        status: ContentStatus | None = None,
        card_kind: CardKind | None = None,
    ) -> tuple[list[ProductRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [*company_scope_filters(Product, scope), Product.deleted_at.is_(None)]
            if status is not None:
                filters.append(Product.status == status)
            total = int(
                await session.scalar(select(func.count()).select_from(Product).where(*filters)) or 0
            )
            rows = (
                await session.scalars(
                    select(Product)
                    .where(*filters)
                    .order_by(Product.sort_order, Product.updated_at.desc(), Product.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_product_record(row) for row in rows], total

    async def get_product(self, *, scope: CatalogScope, product_id: uuid.UUID) -> ProductRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _product_record(await self._product(session, scope, product_id))

    async def create_product(
        self,
        *,
        scope: CatalogScope,
        body: CreateProductRequest,
        trace_id: str | None = None,
    ) -> ProductRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                await self._ensure_product_slug_available(session, scope, body.slug)
                product = Product(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    status=ContentStatus.DRAFT,
                    version=1,
                    **_product_values(body),
                )
                session.add(product)
                await self._audit(
                    session,
                    scope=scope,
                    action="product.create",
                    resource_type="product",
                    resource_id=product.id,
                    trace_id=trace_id,
                    event_data={"slug": product.slug, "version": product.version},
                )
                await session.flush()
                await session.refresh(product)
                return _product_record(product)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_products_company_slug"):
                raise _slug_conflict("产品") from exc
            raise

    async def update_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        body: UpdateProductRequest,
        trace_id: str | None = None,
    ) -> ProductRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                product = await self._product(session, scope, product_id, for_update=True)
                require_version(product.version, expected_version)
                if body.slug != product.slug:
                    await self._ensure_product_slug_available(
                        session, scope, body.slug, exclude_id=product.id
                    )
                for key, value in _product_values(body).items():
                    setattr(product, key, value)
                product.version += 1
                await self._audit(
                    session,
                    scope=scope,
                    action="product.update",
                    resource_type="product",
                    resource_id=product.id,
                    trace_id=trace_id,
                    event_data={"slug": product.slug, "version": product.version},
                )
                await session.flush()
                await session.refresh(product)
                return _product_record(product)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_products_company_slug"):
                raise _slug_conflict("产品") from exc
            raise

    async def publish_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ProductRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            product = await self._product(session, scope, product_id, for_update=True)
            require_version(product.version, expected_version)
            _ensure_product_publishable(product)
            _publish_resource(product, label="产品")
            await self._audit(
                session,
                scope=scope,
                action="product.publish",
                resource_type="product",
                resource_id=product.id,
                trace_id=trace_id,
                event_data={"slug": product.slug, "version": product.version},
            )
            await session.flush()
            await session.refresh(product)
            return _product_record(product)

    async def archive_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ProductRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            product = await self._product(session, scope, product_id, for_update=True)
            require_version(product.version, expected_version)
            _archive_resource(product, label="产品")
            await self._audit(
                session,
                scope=scope,
                action="product.archive",
                resource_type="product",
                resource_id=product.id,
                trace_id=trace_id,
                event_data={"slug": product.slug, "version": product.version},
            )
            await session.flush()
            await session.refresh(product)
            return _product_record(product)

    async def delete_product(
        self,
        *,
        scope: CatalogScope,
        product_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            product = await self._product(session, scope, product_id, for_update=True)
            require_version(product.version, expected_version)
            product.status = ContentStatus.ARCHIVED
            product.deleted_at = datetime.now(UTC)
            product.deleted_by = scope.actor_user_id
            product.version += 1
            await self._audit(
                session,
                scope=scope,
                action="product.delete",
                resource_type="product",
                resource_id=product.id,
                trace_id=trace_id,
                event_data={"slug": product.slug, "version": product.version},
            )

    async def list_case_studies(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        status: ContentStatus | None = None,
    ) -> tuple[list[CaseStudyRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [*company_scope_filters(CaseStudy, scope), CaseStudy.deleted_at.is_(None)]
            if status is not None:
                filters.append(CaseStudy.status == status)
            total = int(
                await session.scalar(select(func.count()).select_from(CaseStudy).where(*filters))
                or 0
            )
            rows = (
                await session.scalars(
                    select(CaseStudy)
                    .where(*filters)
                    .order_by(CaseStudy.sort_order, CaseStudy.updated_at.desc(), CaseStudy.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_case_study_record(row) for row in rows], total

    async def get_case_study(
        self, *, scope: CatalogScope, case_study_id: uuid.UUID
    ) -> CaseStudyRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _case_study_record(await self._case_study(session, scope, case_study_id))

    async def create_case_study(
        self,
        *,
        scope: CatalogScope,
        body: CreateCaseStudyRequest,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                await self._ensure_case_slug_available(session, scope, body.slug)
                case_study = CaseStudy(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    status=ContentStatus.DRAFT,
                    version=1,
                    **_case_study_values(body),
                )
                session.add(case_study)
                await self._audit(
                    session,
                    scope=scope,
                    action="case_study.create",
                    resource_type="case_study",
                    resource_id=case_study.id,
                    trace_id=trace_id,
                    event_data={"slug": case_study.slug, "version": case_study.version},
                )
                await session.flush()
                await session.refresh(case_study)
                return _case_study_record(case_study)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_case_studies_company_slug"):
                raise _slug_conflict("案例") from exc
            raise

    async def update_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        body: UpdateCaseStudyRequest,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        try:
            async with self._sessions() as session, session.begin():
                await self._set_scope(session, scope)
                case_study = await self._case_study(session, scope, case_study_id, for_update=True)
                require_version(case_study.version, expected_version)
                if body.slug != case_study.slug:
                    await self._ensure_case_slug_available(
                        session, scope, body.slug, exclude_id=case_study.id
                    )
                for key, value in _case_study_values(body).items():
                    setattr(case_study, key, value)
                case_study.version += 1
                await self._audit(
                    session,
                    scope=scope,
                    action="case_study.update",
                    resource_type="case_study",
                    resource_id=case_study.id,
                    trace_id=trace_id,
                    event_data={"slug": case_study.slug, "version": case_study.version},
                )
                await session.flush()
                await session.refresh(case_study)
                return _case_study_record(case_study)
        except IntegrityError as exc:
            if _has_constraint(exc, "uq_case_studies_company_slug"):
                raise _slug_conflict("案例") from exc
            raise

    async def publish_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            case_study = await self._case_study(session, scope, case_study_id, for_update=True)
            require_version(case_study.version, expected_version)
            _ensure_case_study_publishable(case_study)
            _publish_resource(case_study, label="案例")
            await self._audit(
                session,
                scope=scope,
                action="case_study.publish",
                resource_type="case_study",
                resource_id=case_study.id,
                trace_id=trace_id,
                event_data={"slug": case_study.slug, "version": case_study.version},
            )
            await session.flush()
            await session.refresh(case_study)
            return _case_study_record(case_study)

    async def archive_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> CaseStudyRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            case_study = await self._case_study(session, scope, case_study_id, for_update=True)
            require_version(case_study.version, expected_version)
            _archive_resource(case_study, label="案例")
            await self._audit(
                session,
                scope=scope,
                action="case_study.archive",
                resource_type="case_study",
                resource_id=case_study.id,
                trace_id=trace_id,
                event_data={"slug": case_study.slug, "version": case_study.version},
            )
            await session.flush()
            await session.refresh(case_study)
            return _case_study_record(case_study)

    async def delete_case_study(
        self,
        *,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            case_study = await self._case_study(session, scope, case_study_id, for_update=True)
            require_version(case_study.version, expected_version)
            case_study.status = ContentStatus.ARCHIVED
            case_study.deleted_at = datetime.now(UTC)
            case_study.deleted_by = scope.actor_user_id
            case_study.version += 1
            await self._audit(
                session,
                scope=scope,
                action="case_study.delete",
                resource_type="case_study",
                resource_id=case_study.id,
                trace_id=trace_id,
                event_data={"slug": case_study.slug, "version": case_study.version},
            )

    async def list_forbidden_topics(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        active: bool | None = None,
    ) -> tuple[list[ForbiddenTopicRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = list(company_scope_filters(ForbiddenTopic, scope))
            if active is not None:
                filters.append(ForbiddenTopic.is_active.is_(active))
            total = int(
                await session.scalar(
                    select(func.count()).select_from(ForbiddenTopic).where(*filters)
                )
                or 0
            )
            rows = (
                await session.scalars(
                    select(ForbiddenTopic)
                    .where(*filters)
                    .order_by(ForbiddenTopic.updated_at.desc(), ForbiddenTopic.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [_forbidden_topic_record(row) for row in rows], total

    async def get_forbidden_topic(
        self, *, scope: CatalogScope, topic_id: uuid.UUID
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _forbidden_topic_record(await self._forbidden_topic(session, scope, topic_id))

    async def create_forbidden_topic(
        self,
        *,
        scope: CatalogScope,
        body: CreateForbiddenTopicRequest,
        trace_id: str | None = None,
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = ForbiddenTopic(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                topic=body.topic,
                match_terms=body.match_terms,
                action=body.action,
                safe_response=body.safe_response,
                is_active=body.is_active,
                version=1,
            )
            session.add(topic)
            await self._audit(
                session,
                scope=scope,
                action="forbidden_topic.create",
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"active": topic.is_active, "version": topic.version},
            )
            await session.flush()
            await session.refresh(topic)
            return _forbidden_topic_record(topic)

    async def update_forbidden_topic(
        self,
        *,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        expected_version: int,
        body: UpdateForbiddenTopicRequest,
        trace_id: str | None = None,
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = await self._forbidden_topic(session, scope, topic_id, for_update=True)
            require_version(topic.version, expected_version)
            topic.topic = body.topic
            topic.match_terms = body.match_terms
            topic.action = body.action
            topic.safe_response = body.safe_response
            topic.version += 1
            await self._audit(
                session,
                scope=scope,
                action="forbidden_topic.update",
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"active": topic.is_active, "version": topic.version},
            )
            await session.flush()
            await session.refresh(topic)
            return _forbidden_topic_record(topic)

    async def set_forbidden_topic_active(
        self,
        *,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        expected_version: int,
        active: bool,
        trace_id: str | None = None,
    ) -> ForbiddenTopicRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = await self._forbidden_topic(session, scope, topic_id, for_update=True)
            require_version(topic.version, expected_version)
            if topic.is_active is active:
                raise ApiError(409, "INVALID_STATE", "禁答主题已经处于目标状态")
            topic.is_active = active
            topic.version += 1
            await self._audit(
                session,
                scope=scope,
                action=("forbidden_topic.activate" if active else "forbidden_topic.deactivate"),
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"active": active, "version": topic.version},
            )
            await session.flush()
            await session.refresh(topic)
            return _forbidden_topic_record(topic)

    async def delete_forbidden_topic(
        self,
        *,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            topic = await self._forbidden_topic(session, scope, topic_id, for_update=True)
            require_version(topic.version, expected_version)
            await self._audit(
                session,
                scope=scope,
                action="forbidden_topic.delete",
                resource_type="forbidden_topic",
                resource_id=topic.id,
                trace_id=trace_id,
                event_data={"version": topic.version},
            )
            await session.delete(topic)

    async def active_forbidden_topics(
        self, *, scope: CatalogScope
    ) -> tuple[ForbiddenTopicRule, ...]:
        """Stable query seam for RAG policy composition; it does not mutate chat flow."""

        return await self.query_active_forbidden_topics(
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    async def query_active_forbidden_topics(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> tuple[ForbiddenTopicRule, ...]:
        """Read active rules from a trusted RAG runtime that has no staff actor."""

        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
            )
            rows = (
                await session.scalars(
                    select(ForbiddenTopic)
                    .where(
                        ForbiddenTopic.tenant_id == tenant_id,
                        ForbiddenTopic.company_id == company_id,
                        ForbiddenTopic.is_active.is_(True),
                    )
                    .order_by(ForbiddenTopic.updated_at.desc(), ForbiddenTopic.id)
                )
            ).all()
            return tuple(
                ForbiddenTopicRule(
                    id=row.id,
                    topic=row.topic,
                    match_terms=tuple(row.match_terms or ()),
                    action=row.action,
                    safe_response=row.safe_response,
                    version=row.version,
                )
                for row in rows
            )

    async def list_cards(
        self,
        *,
        scope: CatalogScope,
        limit: int,
        offset: int,
        status: ContentStatus | None = None,
        card_kind: CardKind | None = None,
    ) -> tuple[list[ManagedCardRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = list(managed_card_filters(scope))
            if status is not None:
                filters.append(Card.status == status)
            if card_kind is not None:
                filters.append(Card.card_kind == card_kind)
            total = int(
                await session.scalar(select(func.count()).select_from(Card).where(*filters)) or 0
            )
            rows = (
                await session.scalars(
                    select(Card)
                    .where(*filters)
                    .order_by(Card.updated_at.desc(), Card.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            records: list[ManagedCardRecord] = []
            for row in rows:
                identity = (
                    await self._employee_identity(
                        session,
                        scope,
                        row.owner_user_id,
                        require_active=False,
                    )
                    if row.card_kind == CardKind.EMPLOYEE
                    else None
                )
                records.append(self._managed_card_record(row, employee_identity=identity))
            return records, total

    async def get_card(self, *, scope: CatalogScope, card_id: uuid.UUID) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id)
            identity = (
                await self._employee_identity(
                    session,
                    scope,
                    card.owner_user_id,
                    require_active=False,
                )
                if card.card_kind == CardKind.EMPLOYEE
                else None
            )
            return self._managed_card_record(card, employee_identity=identity)

    async def create_card(
        self,
        *,
        scope: CatalogScope,
        body: CreateCardRequest,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        if body.card_kind == "enterprise":
            if scope.is_card_owner:
                raise ApiError(403, "FORBIDDEN", "名片所有者不能创建企业官方名片")
            owner_user_id = None
            responsible_user_id = scope.actor_user_id
        else:
            if body.owner_user_id is None and not scope.is_card_owner:
                raise ApiError(422, "EMPLOYEE_SELECTION_REQUIRED", "请选择要绑定的企业员工")
            owner_user_id = body.owner_user_id or scope.actor_user_id
            responsible_user_id = owner_user_id
            if scope.is_card_owner and owner_user_id != scope.actor_user_id:
                raise ApiError(403, "FORBIDDEN", "名片所有者只能为当前账号")
        for _attempt in range(_CARD_SLUG_ATTEMPTS):
            slug = self._slug_factory()
            try:
                return await self._create_card_attempt(
                    scope=scope,
                    body=body,
                    owner_user_id=owner_user_id,
                    responsible_user_id=responsible_user_id,
                    slug=slug,
                    trace_id=trace_id,
                )
            except IntegrityError as exc:
                if _has_constraint(exc, "uq_cards_slug"):
                    continue
                raise
        raise ApiError(503, "CARD_SLUG_UNAVAILABLE", "暂时无法生成安全的名片链接，请重试")

    async def _create_card_attempt(
        self,
        *,
        scope: CatalogScope,
        body: CreateCardRequest,
        owner_user_id: uuid.UUID | None,
        responsible_user_id: uuid.UUID,
        slug: str,
        trace_id: str | None,
    ) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            employee_identity: EmployeeIdentityProjection | None = None
            if body.card_kind == "employee":
                employee_identity = await self._employee_identity(
                    session,
                    scope,
                    owner_user_id,
                    require_active=True,
                    for_update=True,
                )
                await self._ensure_employee_card_available(
                    session,
                    scope=scope,
                    owner_user_id=owner_user_id,
                )
                display_name = employee_identity.display_name
                settings = _employee_card_expression_settings(body)
            else:
                await self._validate_owner(session, scope, responsible_user_id)
                display_name = body.display_name
                settings = _card_settings(body)
            template = await self._resolve_create_template(
                session,
                scope=scope,
                body=body,
            )
            settings["enterprise_template_draft"] = template.model_dump(mode="json")
            card = Card(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                card_kind=CardKind(body.card_kind),
                owner_user_id=owner_user_id,
                responsible_user_id=responsible_user_id,
                slug=slug,
                display_name=display_name,
                status=ContentStatus.DRAFT,
                settings=settings,
                version=1,
            )
            session.add(card)
            await self._audit(
                session,
                scope=scope,
                action="card.create",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={
                    "card_kind": body.card_kind,
                    "owner_user_id": owner_user_id,
                    "slug": slug,
                    "version": card.version,
                },
            )
            await session.flush()
            await session.refresh(card)
            return self._managed_card_record(card, employee_identity=employee_identity)

    async def update_card(
        self,
        *,
        scope: CatalogScope,
        card_id: uuid.UUID,
        expected_version: int,
        body: UpdateManagedCardRequest,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id, for_update=True)
            require_version(card.version, expected_version)
            if body.card_kind != card.card_kind.value:
                raise ApiError(422, "CARD_KIND_IMMUTABLE", "名片类型创建后不能修改")
            if card.card_kind == CardKind.EMPLOYEE:
                if body.owner_user_id is None:
                    raise ApiError(422, "INVALID_CARD_OWNER", "员工名片必须绑定有效员工")
                if scope.is_card_owner and body.owner_user_id != scope.actor_user_id:
                    raise ApiError(403, "FORBIDDEN", "名片所有者不能转移给其他账号")
                employee_identity = await self._employee_identity(
                    session,
                    scope,
                    body.owner_user_id,
                    require_active=True,
                )
                if body.owner_user_id != card.owner_user_id:
                    await self._ensure_employee_card_available(
                        session,
                        scope=scope,
                        owner_user_id=body.owner_user_id,
                        exclude_card_id=card.id,
                    )
                card.owner_user_id = body.owner_user_id
                card.responsible_user_id = body.owner_user_id
                card.display_name = employee_identity.display_name
                card.settings = {
                    **_without_employee_identity(card.settings),
                    **_employee_card_expression_settings(body),
                }
            else:
                employee_identity = None
                card.display_name = body.display_name
                card.settings = {**_template_settings(card.settings), **_card_settings(body)}
            card.version += 1
            await self._audit(
                session,
                scope=scope,
                action="card.update",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={
                    "card_kind": card.card_kind.value,
                    "owner_user_id": card.owner_user_id,
                    "slug": card.slug,
                    "version": card.version,
                },
            )
            await session.flush()
            await session.refresh(card)
            return self._managed_card_record(card, employee_identity=employee_identity)

    async def publish_card(
        self,
        *,
        scope: CatalogScope,
        card_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id, for_update=True)
            require_version(card.version, expected_version)
            employee_identity: EmployeeIdentityProjection | None = None
            settings = _template_settings(card.settings)
            draft = EnterpriseTemplateDocument.model_validate(settings["enterprise_template_draft"])
            published = await self._validate_enterprise_template_resources(
                session,
                scope=scope,
                document=draft,
                require_public_cases=True,
            )
            _require_complete_template_blocks(published)
            settings["enterprise_template_published"] = published.model_dump(mode="json")
            if card.card_kind == CardKind.ENTERPRISE:
                await self._ensure_enterprise_publishable(
                    session,
                    scope=scope,
                    card=card,
                    document=published,
                )
            else:
                employee_identity = await self._employee_identity(
                    session,
                    scope,
                    card.owner_user_id,
                    require_active=True,
                )
                card.display_name = employee_identity.display_name
                settings = _without_employee_identity(settings)
            card.settings = settings
            _ensure_card_publishable(card, employee_identity=employee_identity)
            _publish_card_snapshot(card)
            await self._audit(
                session,
                scope=scope,
                action="card.publish",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={"slug": card.slug, "version": card.version},
            )
            await session.flush()
            await session.refresh(card)
            return self._managed_card_record(card, employee_identity=employee_identity)

    async def get_enterprise_template(
        self, *, scope: CatalogScope, card_id: uuid.UUID
    ) -> EnterpriseTemplateRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id)
            record = _enterprise_template_record(card)
            draft = await self._validate_enterprise_template_resources(
                session,
                scope=scope,
                document=record.draft,
                require_public_cases=False,
            )
            return record.model_copy(update={"draft": draft})

    async def update_enterprise_template(
        self,
        *,
        scope: CatalogScope,
        card_id: uuid.UUID,
        expected_version: int,
        body: UpdateEnterpriseTemplateRequest,
        trace_id: str | None = None,
    ) -> EnterpriseTemplateRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id, for_update=True)
            require_version(card.version, expected_version)
            await self._validate_enterprise_template_resources(
                session,
                scope=scope,
                document=body,
                require_public_cases=False,
            )
            settings = _template_settings(card.settings)
            settings["enterprise_template_draft"] = body.model_dump(mode="json")
            card.settings = settings
            card.version += 1
            await self._audit(
                session,
                scope=scope,
                action="card.composer_template.update",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={"version": card.version, "block_count": len(body.blocks)},
            )
            await session.flush()
            await session.refresh(card)
            return _enterprise_template_record(card)

    async def get_card_composer_default(
        self, *, scope: CatalogScope, card_kind: str
    ) -> CardComposerDefaultRecord:
        kind = _card_kind_value(card_kind)
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            company = await self._company_for_composer(session, scope)
            document = _company_card_composer_default(company.settings, kind)
            return CardComposerDefaultRecord(
                card_kind=kind,
                version=company.version,
                document=document,
            )

    async def update_card_composer_default(
        self,
        *,
        scope: CatalogScope,
        card_kind: str,
        expected_version: int,
        body: UpdateEnterpriseTemplateRequest,
        trace_id: str | None = None,
    ) -> CardComposerDefaultRecord:
        kind = _card_kind_value(card_kind)
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            company = await self._company_for_composer(session, scope, for_update=True)
            require_version(company.version, expected_version)
            await self._validate_enterprise_template_resources(
                session, scope=scope, document=body, require_public_cases=False
            )
            # Persist only canonical references and editor-owned presentation
            # fields. Product/case projections are response-only snapshots.
            document = EnterpriseTemplateDocument.model_validate(body.model_dump(mode="json"))
            settings = _dict_value(company.settings)
            defaults = _dict_value(settings.get("card_composer_defaults"))
            defaults[kind] = document.model_dump(mode="json")
            settings["card_composer_defaults"] = defaults
            company.settings = settings
            company.version += 1
            await self._audit(
                session,
                scope=scope,
                action="company.card_composer_default.update",
                resource_type="company",
                resource_id=company.id,
                trace_id=trace_id,
                event_data={"card_kind": kind, "block_count": len(document.blocks)},
            )
            await session.flush()
            await session.refresh(company)
            return CardComposerDefaultRecord(
                card_kind=kind, version=company.version, document=document
            )

    async def _resolve_card_composer_template(
        self,
        session: AsyncSession,
        *,
        scope: CatalogScope,
        card_kind: str,
        source_card_id: uuid.UUID | None,
    ) -> EnterpriseTemplateDocument:
        kind = _card_kind_value(card_kind)
        if source_card_id is not None:
            source = await self._card(session, scope, source_card_id)
            if source.card_kind.value != kind:
                raise ApiError(422, "TEMPLATE_SOURCE_KIND_MISMATCH", "只能复制同类名片的内容配置")
            document = EnterpriseTemplateDocument.model_validate(
                _template_settings(source.settings)["enterprise_template_draft"]
            )
            await self._validate_enterprise_template_resources(
                session,
                scope=scope,
                document=document,
                require_public_cases=False,
            )
            return document
        company = await self._company_for_composer(session, scope)
        return _company_card_composer_default(company.settings, kind)

    async def _resolve_create_template(
        self,
        session: AsyncSession,
        *,
        scope: CatalogScope,
        body: CreateCardRequest,
    ) -> EnterpriseTemplateDocument:
        if body.template_document is not None:
            await self._validate_enterprise_template_resources(
                session,
                scope=scope,
                document=body.template_document,
                require_public_cases=False,
            )
            # Store the canonical editor document, not the response-only
            # product/case projections returned by resource validation.
            return body.template_document
        return await self._resolve_card_composer_template(
            session,
            scope=scope,
            card_kind=body.card_kind,
            source_card_id=body.template_source_card_id,
        )

    async def _company_for_composer(
        self, session: AsyncSession, scope: CatalogScope, *, for_update: bool = False
    ) -> Company:
        statement = select(Company).where(
            Company.id == scope.company_id,
            Company.tenant_id == scope.tenant_id,
            Company.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        company = await session.scalar(statement)
        if company is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "企业不存在或不在当前作用域")
        return company

    async def _validate_enterprise_template_resources(
        self,
        session: AsyncSession,
        *,
        scope: CatalogScope,
        document: EnterpriseTemplateDocument,
        require_public_cases: bool,
    ) -> EnterpriseTemplateDocument:
        for block in document.blocks:
            if block.case_items or block.product_items:
                raise ApiError(
                    422,
                    "TEMPLATE_SERVER_FIELDS_FORBIDDEN",
                    "产品与案例展示数据由服务端生成",
                )
            for image_url in [*block.image_urls, block.video_cover_url]:
                if image_url and not card_asset_belongs_to_company(image_url, scope.company_id):
                    raise ApiError(
                        422,
                        "TEMPLATE_ASSET_OUT_OF_SCOPE",
                        "模板图片必须来自当前企业的名片素材库",
                    )

        product_ids = {
            product_id
            for block in document.blocks
            if block.type == "business_collection"
            for product_id in block.product_ids
        }
        products: dict[uuid.UUID, Product] = {}
        if product_ids:
            filters = [
                Product.id.in_(product_ids),
                Product.tenant_id == scope.tenant_id,
                Product.company_id == scope.company_id,
                Product.deleted_at.is_(None),
            ]
            if require_public_cases:
                filters.extend(
                    [
                        Product.status == ContentStatus.PUBLISHED,
                        Product.visibility == Visibility.PUBLIC,
                        Product.published_at.is_not(None),
                    ]
                )
            rows = (await session.scalars(select(Product).where(*filters))).all()
            products = {row.id: row for row in rows}
            if set(products) != product_ids:
                raise ApiError(
                    422,
                    "TEMPLATE_PRODUCT_OUT_OF_SCOPE",
                    "模板产品必须属于当前企业并满足公开状态要求",
                )

        case_ids = {
            case_id
            for block in document.blocks
            if block.type == "case_collection"
            for case_id in block.case_ids
        }
        cases: dict[uuid.UUID, CaseStudy] = {}
        if case_ids:
            filters = [
                CaseStudy.id.in_(case_ids),
                CaseStudy.tenant_id == scope.tenant_id,
                CaseStudy.company_id == scope.company_id,
                CaseStudy.deleted_at.is_(None),
            ]
            if require_public_cases:
                filters.extend(
                    [
                        CaseStudy.status == ContentStatus.PUBLISHED,
                        CaseStudy.visibility == Visibility.PUBLIC,
                        CaseStudy.published_at.is_not(None),
                    ]
                )
            rows = (await session.scalars(select(CaseStudy).where(*filters))).all()
            cases = {row.id: row for row in rows}
            if set(cases) != case_ids:
                raise ApiError(
                    422,
                    "TEMPLATE_CASE_OUT_OF_SCOPE",
                    "模板案例必须属于当前企业并满足公开状态要求",
                )

        faq_document_ids = {
            document_id
            for block in document.blocks
            if block.type == "faq" and block.faq_mode == "selected"
            for document_id in block.faq_document_ids
        }
        if faq_document_ids:
            valid_faq_ids = set(
                (
                    await session.scalars(
                        eligible_faq_document_statement(scope, faq_document_ids)
                    )
                ).all()
            )
            if valid_faq_ids != faq_document_ids:
                raise ApiError(
                    422,
                    "TEMPLATE_FAQ_OUT_OF_SCOPE",
                    "模板问答必须是当前企业已发布且公开的 FAQ",
                )

        projected_blocks = []
        for block in document.blocks:
            product_items = [
                {
                    "id": str(product.id),
                    "slug": product.slug,
                    "name": product.name,
                    "category": product.category,
                    "summary": product.summary,
                    "image_url": product.image_url,
                }
                for product_id in block.product_ids
                if (product := products.get(product_id)) is not None
            ]
            case_items = [
                {
                    "id": str(case.id),
                    "slug": case.slug,
                    "title": case.title,
                    "industry": case.industry,
                    "summary": case.result,
                    "image_url": case.image_url,
                }
                for case_id in block.case_ids
                if (case := cases.get(case_id)) is not None
            ]
            projected_blocks.append(
                block.model_copy(update={"product_items": product_items, "case_items": case_items})
            )
        return document.model_copy(update={"blocks": projected_blocks})

    async def _ensure_enterprise_publishable(
        self,
        session: AsyncSession,
        *,
        scope: CatalogScope,
        card: Card,
        document: EnterpriseTemplateDocument,
    ) -> None:
        company = await session.get(Company, scope.company_id)
        company_settings = _dict_value(company.settings if company is not None else {})
        settings = _dict_value(card.settings)
        missing: list[str] = []
        if company is None or not company.name.strip():
            missing.append("company_name")
        if not (_string_value(settings.get("title")) or "").strip():
            missing.append("business_positioning")
        brand_asset = _string_value(settings.get("avatar_url")) or _string_value(
            company_settings.get("logo_url")
        )
        if not brand_asset:
            missing.append("brand_identity")
        website = _string_value(company_settings.get("website"))
        contact_field = await session.scalar(
            select(CardContactField.id)
            .where(
                CardContactField.tenant_id == scope.tenant_id,
                CardContactField.company_id == scope.company_id,
                CardContactField.card_id == card.id,
                CardContactField.is_active.is_(True),
                CardContactField.visibility == Visibility.PUBLIC,
            )
            .limit(1)
        )
        wecom_contact = await session.scalar(
            select(WeComCardContactWay.id)
            .where(
                WeComCardContactWay.tenant_id == scope.tenant_id,
                WeComCardContactWay.company_id == scope.company_id,
                WeComCardContactWay.card_id == card.id,
                WeComCardContactWay.revoked_at.is_(None),
            )
            .limit(1)
        )
        template_contact = any(
            block.visible
            and ((block.type == "cta" and bool(block.cta_url)) or block.type == "ai_assistant")
            for block in document.blocks
        )
        if not website and contact_field is None and wecom_contact is None and not template_contact:
            missing.append("contact_route")
        if missing:
            raise ApiError(
                422,
                "ENTERPRISE_TEMPLATE_NOT_PUBLISHABLE",
                "企业名片发布检查未通过",
                details={"fields": missing},
            )

    async def deactivate_card(
        self,
        *,
        scope: CatalogScope,
        card_id: uuid.UUID,
        expected_version: int,
        trace_id: str | None = None,
    ) -> ManagedCardRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, card_id, for_update=True)
            require_version(card.version, expected_version)
            _archive_resource(card, label="名片")
            await self._audit(
                session,
                scope=scope,
                action="card.deactivate",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={"slug": card.slug, "version": card.version},
            )
            await session.flush()
            await session.refresh(card)
            employee_identity = (
                await self._employee_identity(
                    session,
                    scope,
                    card.owner_user_id,
                    require_active=False,
                )
                if card.card_kind == CardKind.EMPLOYEE
                else None
            )
            return self._managed_card_record(card, employee_identity=employee_identity)

    async def list_public_products(
        self,
        *,
        card_slug: str,
        limit: int,
        offset: int,
    ) -> tuple[list[PublicProductRecord], int]:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            filters = public_content_filters(
                Product,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
            rows = (
                await session.scalars(
                    select(Product)
                    .where(*filters)
                    .order_by(Product.sort_order, Product.published_at.desc(), Product.id)
                )
            ).all()
            overrides = await effective_overrides(
                session, scope=scope, resource_type="product", resource_ids=[row.id for row in rows]
            )
            records = [
                _public_product_record(row, overrides[row.id].custom_display)
                for row in rows
                if overrides[row.id].visible
            ]
            records.sort(key=lambda item: (item.sort_order, item.published_at, item.slug))
            return records[offset : offset + limit], len(records)

    async def get_public_product(self, *, card_slug: str, product_slug: str) -> PublicProductRecord:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            product = await session.scalar(
                select(Product).where(
                    *public_content_filters(
                        Product,
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                    ),
                    _public_identifier_filter(Product, product_slug),
                )
            )
            if product is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "产品不存在或尚未公开")
            resolved = (
                await effective_overrides(
                    session, scope=scope, resource_type="product", resource_ids=[product.id]
                )
            )[product.id]
            if not resolved.visible:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "产品不存在或尚未公开")
            return _public_product_record(product, resolved.custom_display)

    async def list_public_case_studies(
        self,
        *,
        card_slug: str,
        limit: int,
        offset: int,
    ) -> tuple[list[PublicCaseStudyRecord], int]:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            filters = public_content_filters(
                CaseStudy,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
            rows = (
                await session.scalars(
                    select(CaseStudy)
                    .where(*filters)
                    .order_by(CaseStudy.sort_order, CaseStudy.published_at.desc(), CaseStudy.id)
                )
            ).all()
            overrides = await effective_overrides(
                session,
                scope=scope,
                resource_type="case_study",
                resource_ids=[row.id for row in rows],
            )
            records = [
                _public_case_study_record(row, overrides[row.id].custom_display)
                for row in rows
                if overrides[row.id].visible
            ]
            records.sort(key=lambda item: (item.sort_order, item.published_at, item.slug))
            return records[offset : offset + limit], len(records)

    async def get_public_case_study(
        self, *, card_slug: str, case_study_slug: str
    ) -> PublicCaseStudyRecord:
        async with self._sessions() as session, session.begin():
            scope = await resolve_public_card_scope(session, card_slug)
            if scope is None:
                raise ApiError(404, "CARD_NOT_FOUND", "名片不存在或尚未发布")
            case_study = await session.scalar(
                select(CaseStudy).where(
                    *public_content_filters(
                        CaseStudy,
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                    ),
                    _public_identifier_filter(CaseStudy, case_study_slug),
                )
            )
            if case_study is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "案例不存在或尚未公开")
            resolved = (
                await effective_overrides(
                    session, scope=scope, resource_type="case_study", resource_ids=[case_study.id]
                )
            )[case_study.id]
            if not resolved.visible:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "案例不存在或尚未公开")
            return _public_case_study_record(case_study, resolved.custom_display)

    async def _set_scope(self, session: AsyncSession, scope: CatalogScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    async def _product(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        product_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Product:
        statement = select(Product).where(
            *company_scope_filters(Product, scope),
            Product.id == product_id,
            Product.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        product = await session.scalar(statement)
        if product is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "产品不存在或不在当前作用域")
        return product

    async def _case_study(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        case_study_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> CaseStudy:
        statement = select(CaseStudy).where(
            *company_scope_filters(CaseStudy, scope),
            CaseStudy.id == case_study_id,
            CaseStudy.deleted_at.is_(None),
        )
        if for_update:
            statement = statement.with_for_update()
        case_study = await session.scalar(statement)
        if case_study is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "案例不存在或不在当前作用域")
        return case_study

    async def _forbidden_topic(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        topic_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> ForbiddenTopic:
        statement = select(ForbiddenTopic).where(
            *company_scope_filters(ForbiddenTopic, scope),
            ForbiddenTopic.id == topic_id,
        )
        if for_update:
            statement = statement.with_for_update()
        topic = await session.scalar(statement)
        if topic is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "禁答主题不存在或不在当前作用域")
        return topic

    async def _card(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        card_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Card:
        statement = select(Card).where(*managed_card_filters(scope), Card.id == card_id)
        if for_update:
            statement = statement.with_for_update()
        card = await session.scalar(statement)
        if card is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在或不在当前作用域")
        return card

    async def _ensure_product_slug_available(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        slug: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        statement = select(Product.id).where(
            *company_scope_filters(Product, scope),
            Product.slug == slug,
        )
        if exclude_id is not None:
            statement = statement.where(Product.id != exclude_id)
        if await session.scalar(statement) is not None:
            raise _slug_conflict("产品")

    async def _ensure_case_slug_available(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        slug: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        statement = select(CaseStudy.id).where(
            *company_scope_filters(CaseStudy, scope),
            CaseStudy.slug == slug,
        )
        if exclude_id is not None:
            statement = statement.where(CaseStudy.id != exclude_id)
        if await session.scalar(statement) is not None:
            raise _slug_conflict("案例")

    async def _validate_owner(
        self, session: AsyncSession, scope: CatalogScope, owner_user_id: uuid.UUID
    ) -> None:
        membership_id = await session.scalar(
            select(Membership.id).where(
                Membership.user_id == owner_user_id,
                Membership.tenant_id == scope.tenant_id,
                Membership.company_id == scope.company_id,
                Membership.status == LifecycleStatus.ACTIVE,
            )
        )
        if membership_id is None:
            raise ApiError(422, "INVALID_CARD_OWNER", "名片所有者不是当前企业的有效成员")

    async def _employee_identity(
        self,
        session: AsyncSession,
        scope: CatalogScope,
        owner_user_id: uuid.UUID | None,
        *,
        require_active: bool,
        for_update: bool = False,
    ) -> EmployeeIdentityProjection:
        if owner_user_id is None:
            raise ApiError(422, "INVALID_CARD_OWNER", "员工名片必须绑定有效员工")
        statement = (
            select(
                User.display_name.label("display_name"),
                User.status.label("user_status"),
                User.deleted_at.label("user_deleted_at"),
                Membership.job_title.label("job_title"),
                Membership.avatar_url.label("avatar_url"),
                Membership.business_summary.label("business_summary"),
                Membership.status.label("membership_status"),
            )
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == owner_user_id,
                Membership.tenant_id == scope.tenant_id,
                Membership.company_id == scope.company_id,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await session.execute(statement)).mappings().one_or_none()
        if row is None or row["user_deleted_at"] is not None:
            raise ApiError(422, "INVALID_CARD_OWNER", "员工身份资料不存在或不在当前企业")
        if require_active and (
            row["user_status"] != LifecycleStatus.ACTIVE
            or row["membership_status"] != LifecycleStatus.ACTIVE
        ):
            raise ApiError(422, "INVALID_CARD_OWNER", "员工身份已停用，无法修改或发布名片")
        return EmployeeIdentityProjection(
            display_name=str(row["display_name"]),
            job_title=_string_value(row["job_title"]),
            avatar_url=_string_value(row["avatar_url"]),
            business_summary=_string_value(row["business_summary"]),
        )

    async def _ensure_employee_card_available(
        self,
        session: AsyncSession,
        *,
        scope: CatalogScope,
        owner_user_id: uuid.UUID,
        exclude_card_id: uuid.UUID | None = None,
    ) -> None:
        statement = select(Card.id).where(
            Card.tenant_id == scope.tenant_id,
            Card.company_id == scope.company_id,
            Card.card_kind == CardKind.EMPLOYEE,
            Card.owner_user_id == owner_user_id,
            Card.deleted_at.is_(None),
        )
        if exclude_card_id is not None:
            statement = statement.where(Card.id != exclude_card_id)
        if await session.scalar(statement.limit(1)) is not None:
            raise ApiError(
                409,
                "EMPLOYEE_CARD_EXISTS",
                "该企业员工已经拥有员工名片，请直接编辑已有名片",
            )

    async def _audit(
        self,
        session: AsyncSession,
        *,
        scope: CatalogScope,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None,
        trace_id: str | None,
        event_data: dict[str, Any],
    ) -> None:
        await append_audit(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            actor_user_id=scope.actor_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            trace_id=trace_id,
            event_data=event_data,
        )

    def _managed_card_record(
        self,
        card: Card,
        *,
        employee_identity: EmployeeIdentityProjection | None = None,
    ) -> ManagedCardRecord:
        settings = _dict_value(card.settings)
        share_url = f"{self._public_card_base_url}/c/{card.slug}"
        display_name = (
            employee_identity.display_name if employee_identity is not None else card.display_name
        )
        title = (
            employee_identity.job_title
            if employee_identity is not None
            else _string_value(settings.get("title"))
        )
        avatar_url = (
            employee_identity.avatar_url
            if employee_identity is not None
            else _string_value(settings.get("avatar_url"))
        )
        return ManagedCardRecord(
            id=card.id,
            card_kind=card.card_kind.value,
            owner_user_id=card.owner_user_id,
            slug=card.slug,
            display_name=display_name,
            title=title or display_name,
            avatar_url=avatar_url,
            assistant_name=_string_value(settings.get("assistant_name")),
            welcome_message=_string_value(settings.get("welcome_message")),
            suggested_questions=_string_list(settings.get("suggested_questions"), limit=6),
            policy_versions=_string_dict(settings.get("policy_versions")),
            employee_contact_visibility=_employee_contact_visibility(settings),
            status=card.status.value,
            published_at=card.published_at,
            version=card.version,
            share_url=share_url,
            qr_url=share_url,
            created_at=card.created_at,
            updated_at=card.updated_at,
        )


def _product_values(body: CreateProductRequest | UpdateProductRequest) -> dict[str, Any]:
    return {
        "slug": body.slug,
        "name": body.name,
        "category": body.category,
        "summary": body.summary,
        "detail": body.detail,
        "audience": body.audience,
        "price_boundary": body.price_boundary,
        "image_url": body.image_url,
        "visibility": Visibility(body.visibility),
        "sort_order": body.sort_order,
        "settings": dict(body.settings),
    }


def _case_study_values(
    body: CreateCaseStudyRequest | UpdateCaseStudyRequest,
) -> dict[str, Any]:
    return {
        "slug": body.slug,
        "title": body.title,
        "industry": body.industry,
        "background": body.background,
        "solution": body.solution,
        "result": body.result,
        "client_display_name": body.client_display_name,
        "image_url": body.image_url,
        "visibility": Visibility(body.visibility),
        "sort_order": body.sort_order,
        "settings": dict(body.settings),
    }


def _card_settings(body: CreateCardRequest | UpdateManagedCardRequest) -> dict[str, Any]:
    return {
        "title": body.title,
        "avatar_url": body.avatar_url,
        "assistant_name": body.assistant_name,
        "welcome_message": body.welcome_message,
        "suggested_questions": list(body.suggested_questions),
        "policy_versions": dict(body.policy_versions),
    }


def _employee_card_expression_settings(
    body: CreateCardRequest | UpdateManagedCardRequest,
) -> dict[str, Any]:
    """Persist employee-card expression only; identity belongs to the membership."""

    return {
        "assistant_name": body.assistant_name,
        "welcome_message": body.welcome_message,
        "suggested_questions": list(body.suggested_questions),
        "policy_versions": dict(body.policy_versions),
        "employee_contact_visibility": list(body.employee_contact_visibility),
    }


def _without_employee_identity(value: object) -> dict[str, Any]:
    settings = _dict_value(value)
    for key in ("title", "avatar_url", "business_summary"):
        settings.pop(key, None)
    return settings


def _employee_contact_visibility(value: object) -> list[str]:
    settings = _dict_value(value)
    raw = settings.get("employee_contact_visibility")
    # Existing employee cards predate explicit consent controls. Keep their
    # public contract stable until an administrator saves an explicit choice.
    if raw is None:
        return ["mobile", "email"]
    if not isinstance(raw, list):
        return []
    return [field for field in ("mobile", "email") if field in raw]


def _default_enterprise_template() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "theme_key": "brand",
        "blocks": [
            {
                "id": "identity",
                "type": "identity",
                "visible": True,
                "directory_enabled": False,
                "sort_order": 0,
                "title": "基础名片",
            },
            {
                "id": "overview",
                "type": "rich_text",
                "visible": True,
                "sort_order": 1,
                "title": "概览",
            },
            {
                "id": "intro",
                "type": "rich_text",
                "visible": True,
                "sort_order": 2,
                "title": "企业介绍",
            },
            {
                "id": "business",
                "type": "business_collection",
                "visible": True,
                "sort_order": 3,
                "title": "核心业务",
            },
            {
                "id": "cases",
                "type": "case_collection",
                "visible": True,
                "sort_order": 4,
                "title": "代表案例",
            },
            {
                "id": "trust",
                "type": "trust_panel",
                "visible": True,
                "sort_order": 5,
                "title": "企业资料",
            },
            {"id": "faq", "type": "faq", "visible": True, "sort_order": 6, "title": "常见问题"},
            {
                "id": "ai",
                "type": "ai_assistant",
                "visible": True,
                "sort_order": 7,
                "title": "企业 AI 助手",
            },
        ],
    }


def _merge_default_template_blocks(blocks: list[object]) -> list[object]:
    indexed = [(index, block) for index, block in enumerate(blocks) if isinstance(block, dict)]
    merged = [
        block
        for _, block in sorted(
            indexed,
            key=lambda item: (
                item[1].get("sort_order")
                if isinstance(item[1].get("sort_order"), int)
                else item[0],
                item[0],
            ),
        )
    ]
    defaults = _default_enterprise_template()["blocks"]
    matched_default_ids: set[str] = set()

    def matches_default(block: dict[str, Any], default_block: dict[str, Any]) -> bool:
        return bool(
            block.get("id") == default_block["id"]
            or (default_block["type"] != "rich_text" and block.get("type") == default_block["type"])
            or (
                default_block["type"] == "rich_text"
                and block.get("type") == "rich_text"
                and block.get("title") == default_block.get("title")
            )
        )

    for index, block in enumerate(merged):
        match = next(
            (
                default_block
                for default_block in defaults
                if default_block["id"] not in matched_default_ids
                and matches_default(block, default_block)
            ),
            None,
        )
        if match is None:
            continue
        matched_default_ids.add(match["id"])
        if match["type"] == "identity":
            merged[index] = {
                **block,
                "visible": True,
                "directory_enabled": block.get(
                    "directory_enabled", match["directory_enabled"]
                ),
            }

    for default_block in defaults:
        if default_block["id"] in matched_default_ids:
            continue
        insert_at = min(int(default_block["sort_order"]), len(merged))
        merged.insert(insert_at, default_block)
    return [{**block, "sort_order": index} for index, block in enumerate(merged)]


def _require_complete_template_blocks(document: EnterpriseTemplateDocument) -> None:
    incomplete: list[str] = []
    for block in document.blocks:
        if not block.visible:
            continue
        if block.type == "image_gallery" and not block.image_urls:
            incomplete.append(block.id)
        elif block.type == "video_link" and (not block.video_url or not block.video_cover_url):
            incomplete.append(block.id)
        elif (
            block.type == "business_collection" and block.id != "business" and not block.product_ids
        ):
            incomplete.append(block.id)
        elif block.type == "case_collection" and block.id != "cases" and not block.case_ids:
            incomplete.append(block.id)
        elif block.type == "faq" and block.faq_mode == "selected" and not block.faq_document_ids:
            incomplete.append(block.id)
        elif block.type == "cta" and (not block.cta_label or not block.cta_url):
            incomplete.append(block.id)
    if incomplete:
        raise ApiError(
            422,
            "TEMPLATE_BLOCK_INCOMPLETE",
            "公开名片不能包含未完成的自由模块",
            details={"block_ids": incomplete},
        )


def _card_kind_value(value: str) -> str:
    if value not in {"enterprise", "employee"}:
        raise ApiError(422, "INVALID_CARD_KIND", "名片类型必须是 enterprise 或 employee")
    return value


def _company_card_composer_default(value: object, card_kind: str) -> EnterpriseTemplateDocument:
    settings = _dict_value(value)
    defaults = _dict_value(settings.get("card_composer_defaults"))
    candidate = defaults.get(card_kind)
    if isinstance(candidate, dict):
        try:
            return EnterpriseTemplateDocument.model_validate(
                {**candidate, "blocks": _merge_default_template_blocks(candidate.get("blocks", []))}
            )
        except ValueError:
            pass
    return EnterpriseTemplateDocument.model_validate(_default_enterprise_template())


def card_asset_belongs_to_company(value: str, company_id: uuid.UUID) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    try:
        public_index = parts.index("public")
    except ValueError:
        return False
    suffix = parts[public_index:]
    if len(suffix) != 4 or suffix[:2] != ["public", "card-assets"]:
        return False
    if suffix[2] != str(company_id):
        return False
    filename = suffix[3]
    if not filename.endswith(".webp"):
        return False
    try:
        uuid.UUID(filename.removesuffix(".webp"))
    except ValueError:
        return False
    return True


def _template_settings(value: object) -> dict[str, Any]:
    settings = _dict_value(value)
    for key in ("enterprise_template_draft", "enterprise_template_published"):
        document = settings.get(key)
        if key == "enterprise_template_draft" and not isinstance(document, dict):
            settings[key] = _default_enterprise_template()
            continue
        if not isinstance(document, dict):
            continue
        blocks = document.get("blocks")
        if isinstance(blocks, list):
            settings[key] = {
                **document,
                "blocks": _merge_default_template_blocks(blocks),
            }
    return settings


def _enterprise_template_record(card: Card) -> EnterpriseTemplateRecord:
    settings = _template_settings(card.settings)
    return EnterpriseTemplateRecord(
        card_id=card.id,
        version=card.version,
        draft=EnterpriseTemplateDocument.model_validate(settings["enterprise_template_draft"]),
        published=(
            EnterpriseTemplateDocument.model_validate(settings["enterprise_template_published"])
            if isinstance(settings.get("enterprise_template_published"), dict)
            else None
        ),
    )


def _product_record(product: Product) -> ProductRecord:
    return ProductRecord(
        id=product.id,
        slug=product.slug,
        name=product.name,
        category=product.category,
        summary=product.summary,
        detail=product.detail,
        audience=product.audience,
        price_boundary=product.price_boundary,
        image_url=product.image_url,
        visibility=product.visibility.value,
        sort_order=product.sort_order,
        settings=_dict_value(product.settings),
        status=product.status.value,
        published_at=product.published_at,
        version=product.version,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


def _case_study_record(case_study: CaseStudy) -> CaseStudyRecord:
    return CaseStudyRecord(
        id=case_study.id,
        slug=case_study.slug,
        title=case_study.title,
        industry=case_study.industry,
        background=case_study.background,
        solution=case_study.solution,
        result=case_study.result,
        client_display_name=case_study.client_display_name,
        image_url=case_study.image_url,
        visibility=case_study.visibility.value,
        sort_order=case_study.sort_order,
        settings=_dict_value(case_study.settings),
        status=case_study.status.value,
        published_at=case_study.published_at,
        version=case_study.version,
        created_at=case_study.created_at,
        updated_at=case_study.updated_at,
    )


def _forbidden_topic_record(topic: ForbiddenTopic) -> ForbiddenTopicRecord:
    return ForbiddenTopicRecord(
        id=topic.id,
        topic=topic.topic,
        match_terms=list(topic.match_terms or ()),
        action=topic.action,
        safe_response=topic.safe_response,
        is_active=topic.is_active,
        version=topic.version,
        created_at=topic.created_at,
        updated_at=topic.updated_at,
    )


def _public_product_record(
    product: Product, display: dict[str, Any] | None = None
) -> PublicProductRecord:
    if product.published_at is None:
        raise RuntimeError("public product is missing published_at")
    custom = display or {}
    return PublicProductRecord(
        slug=product.slug,
        name=str(custom.get("title") or product.name),
        category=product.category,
        summary=str(custom.get("summary") or product.summary),
        detail=product.detail,
        audience=product.audience,
        price_boundary=product.price_boundary,
        image_url=str(custom.get("image_url") or product.image_url)
        if (custom.get("image_url") or product.image_url)
        else None,
        sort_order=int(custom.get("sort_order", product.sort_order)),
        published_at=product.published_at,
    )


def _public_case_study_record(
    case_study: CaseStudy, display: dict[str, Any] | None = None
) -> PublicCaseStudyRecord:
    if case_study.published_at is None:
        raise RuntimeError("public case study is missing published_at")
    custom = display or {}
    return PublicCaseStudyRecord(
        slug=case_study.slug,
        title=str(custom.get("title") or case_study.title),
        industry=case_study.industry,
        background=case_study.background,
        solution=case_study.solution,
        result=case_study.result,
        client_display_name=case_study.client_display_name,
        image_url=str(custom.get("image_url") or case_study.image_url)
        if (custom.get("image_url") or case_study.image_url)
        else None,
        sort_order=int(custom.get("sort_order", case_study.sort_order)),
        published_at=case_study.published_at,
    )


def _ensure_product_publishable(product: Product) -> None:
    missing = [
        field
        for field, value in {
            "name": product.name,
            "summary": product.summary,
            "detail": product.detail,
        }.items()
        if not isinstance(value, str) or not value.strip()
    ]
    _ensure_publishable_asset(product.image_url, missing=missing, field_name="image_url")
    if missing:
        raise ApiError(
            422,
            "CONTENT_NOT_PUBLISHABLE",
            "产品信息不完整，暂时无法发布",
            details={"fields": missing},
        )


def _ensure_case_study_publishable(case_study: CaseStudy) -> None:
    missing = [
        field
        for field, value in {
            "title": case_study.title,
            "background": case_study.background,
            "solution": case_study.solution,
            "result": case_study.result,
        }.items()
        if not isinstance(value, str) or not value.strip()
    ]
    _ensure_publishable_asset(case_study.image_url, missing=missing, field_name="image_url")
    if missing:
        raise ApiError(
            422,
            "CONTENT_NOT_PUBLISHABLE",
            "案例信息不完整，暂时无法发布",
            details={"fields": missing},
        )


def _ensure_card_publishable(
    card: Card,
    *,
    employee_identity: EmployeeIdentityProjection | None = None,
) -> None:
    settings = _dict_value(card.settings)
    missing: list[str] = []
    display_name = (
        employee_identity.display_name if employee_identity is not None else card.display_name
    )
    title = (
        employee_identity.job_title
        if employee_identity is not None
        else _string_value(settings.get("title"))
    )
    avatar_url = (
        employee_identity.avatar_url
        if employee_identity is not None
        else _string_value(settings.get("avatar_url"))
    )
    if not display_name.strip():
        missing.append("display_name")
    if not (title or "").strip():
        missing.append("title")
    _ensure_publishable_asset(
        avatar_url,
        missing=missing,
        field_name="avatar_url",
    )
    if missing:
        raise ApiError(
            422,
            "CONTENT_NOT_PUBLISHABLE",
            "名片信息不完整，暂时无法发布",
            details={"fields": missing},
        )


def _ensure_publishable_asset(
    value: str | None,
    *,
    missing: list[str],
    field_name: str,
) -> None:
    try:
        validate_safe_asset_url(value)
    except ValueError:
        missing.append(field_name)


def _publish_resource(resource: Any, *, label: str) -> None:
    if resource.status == ContentStatus.PUBLISHED:
        raise ApiError(409, "INVALID_STATE", f"{label}已经发布")
    resource.status = ContentStatus.PUBLISHED
    resource.published_at = datetime.now(UTC)
    resource.version += 1


def _publish_card_snapshot(card: Card) -> None:
    """Publish a draft card or replace the public snapshot of a live card."""
    if card.status == ContentStatus.PUBLISHED:
        card.published_at = datetime.now(UTC)
        card.version += 1
        return
    _publish_resource(card, label="名片")


def _archive_resource(resource: Any, *, label: str) -> None:
    if resource.status == ContentStatus.ARCHIVED:
        raise ApiError(409, "INVALID_STATE", f"{label}已经归档")
    resource.status = ContentStatus.ARCHIVED
    resource.version += 1


def _slug_conflict(label: str) -> ApiError:
    return ApiError(409, "SLUG_CONFLICT", f"{label}链接标识已存在，请更换后重试")


def _public_identifier_filter(model: Any, value: str) -> Any:
    try:
        resource_id = uuid.UUID(value)
    except ValueError:
        return model.slug == value
    return or_(model.id == resource_id, model.slug == value)


def _has_constraint(exc: IntegrityError, name: str) -> bool:
    candidates: list[object | None] = [exc, exc.orig]
    candidates.extend(
        [
            getattr(exc.orig, "__cause__", None),
            getattr(exc.orig, "__context__", None),
        ]
    )
    for candidate in candidates:
        if candidate is None:
            continue
        diagnostic = getattr(candidate, "diag", None)
        constraint = getattr(diagnostic, "constraint_name", None) or getattr(
            candidate, "constraint_name", None
        )
        if constraint == name or name in str(candidate):
            return True
    return False


def _normalize_public_base_url(
    value: str,
    *,
    allow_insecure_http: bool = False,
) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("public_card_base_url must be an absolute HTTP(S) origin or base path")
    if (
        parsed.scheme.casefold() == "http"
        and parsed.hostname not in {"localhost", "127.0.0.1"}
        and not allow_insecure_http
    ):
        raise ValueError("non-local public_card_base_url must use HTTPS")
    return candidate


def _dict_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)][:limit]


def _string_dict(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


__all__ = [
    "CatalogScope",
    "CatalogStore",
    "ForbiddenTopicRule",
    "company_scope_filters",
    "generate_card_slug",
    "is_public_content",
    "managed_card_filters",
    "public_content_filters",
    "require_version",
]
