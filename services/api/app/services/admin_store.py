from __future__ import annotations

import asyncio
import hashlib
import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import (
    EmbeddingProviderConfig,
    HttpxJsonTransport,
    OpenAICompatibleEmbeddingProvider,
    ProviderCredentials,
)
from app.ai.protocols import EmbeddingProvider
from app.api.admin_schemas import (
    CardProfile,
    CompanyProfile,
    CreateKnowledgeDocumentRequest,
    KnowledgeDocumentDetail,
    KnowledgeDocumentRecord,
    KnowledgeDraftResult,
    KnowledgePublishResult,
    KnowledgeVersionSummary,
    PutKnowledgeDocumentRequest,
    SelectableFaqRecord,
    UpdateCardRequest,
    UpdateCompanyProfileRequest,
)
from app.api.errors import ApiError
from app.core.config import Settings
from app.db.models import (
    EMBEDDING_DIMENSION,
    Card,
    Company,
    ContentStatus,
    IndexJobStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndexJob,
    KnowledgeVersion,
    ReviewStatus,
    Visibility,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit

logger = structlog.get_logger(__name__)
_EMBEDDING_BATCH_SIZE = 64
_CHUNK_MAX_CHARS = 1_600


@dataclass(frozen=True, slots=True)
class AdminScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class PreparedChunk:
    id: uuid.UUID
    title: str
    text: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class PreparedPublish:
    document_id: uuid.UUID
    document_version: int
    version_id: uuid.UUID
    version_number: int
    job_id: uuid.UUID
    chunks: tuple[PreparedChunk, ...]


def selectable_faq_filters(scope: AdminScope) -> tuple[Any, ...]:
    """Strict public-safe eligibility used by the card editor FAQ picker."""

    active_public_chunk = (
        select(KnowledgeChunk.id)
        .where(
            KnowledgeChunk.tenant_id == scope.tenant_id,
            KnowledgeChunk.company_id == scope.company_id,
            KnowledgeChunk.document_id == KnowledgeDocument.id,
            KnowledgeChunk.version_id == KnowledgeDocument.current_version_id,
            KnowledgeChunk.is_active.is_(True),
            KnowledgeChunk.visibility == Visibility.PUBLIC,
        )
        .exists()
    )
    return (
        KnowledgeDocument.tenant_id == scope.tenant_id,
        KnowledgeDocument.company_id == scope.company_id,
        KnowledgeDocument.source_type == "faq",
        KnowledgeDocument.status == ContentStatus.PUBLISHED,
        KnowledgeDocument.current_version_id.is_not(None),
        active_public_chunk,
    )


class AdminStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._embedding_provider = embedding_provider

    @classmethod
    def from_runtime(
        cls,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> AdminStore:
        provider: EmbeddingProvider | None = None
        if settings.embedding_provider:
            if settings.embedding_base_url is None or settings.embedding_model is None:
                raise RuntimeError("embedding provider configuration is incomplete")
            provider = OpenAICompatibleEmbeddingProvider(
                EmbeddingProviderConfig(
                    base_url=settings.embedding_base_url,
                    model=settings.embedding_model,
                    provider_name=settings.embedding_provider,
                    timeout_seconds=settings.embedding_timeout_seconds,
                    dimensions=EMBEDDING_DIMENSION,
                    max_batch_size=_EMBEDDING_BATCH_SIZE,
                ),
                transport=HttpxJsonTransport(http_client),
            )
        return cls(session_factory, settings, embedding_provider=provider)

    async def get_company_profile(self, *, scope: AdminScope) -> CompanyProfile:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            company = await self._company(session, scope)
            return _company_profile(company)

    async def update_company_profile(
        self,
        *,
        scope: AdminScope,
        expected_version: int,
        body: UpdateCompanyProfileRequest,
        trace_id: str | None = None,
    ) -> CompanyProfile:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            company = await self._company(session, scope, for_update=True)
            _require_version(company.version, expected_version)

            company.name = body.name
            company.normalized_name = body.name.casefold()
            company.industry = body.industry
            settings = _dict_value(company.settings)
            policy_versions = _dict_value(settings.get("policy_versions"))
            previous_profile_policy = _string_value(
                policy_versions.get("profile_personalization")
            ) or "profile-personalization-v1"
            policy_versions["profile_personalization"] = (
                body.profile_personalization_policy_version
            )
            settings.update(
                {
                    "summary": body.summary,
                    "region": body.region,
                    "website": _url_value(body.website),
                    "logo_url": _url_value(body.logo_url),
                    "policy_versions": policy_versions,
                }
            )
            company.settings = settings
            company.version += 1
            await self._audit(
                session,
                scope=scope,
                action="company.profile.update",
                resource_type="company",
                resource_id=company.id,
                trace_id=trace_id,
                event_data={
                    "version": company.version,
                    "profile_policy_changed": (
                        previous_profile_policy
                        != body.profile_personalization_policy_version
                    ),
                },
            )
            await session.flush()
            await session.refresh(company)
            return _company_profile(company)

    async def get_card(self, *, scope: AdminScope) -> CardProfile:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope)
            return _card_profile(card)

    async def update_card(
        self,
        *,
        scope: AdminScope,
        expected_version: int,
        body: UpdateCardRequest,
        trace_id: str | None = None,
    ) -> CardProfile:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            card = await self._card(session, scope, for_update=True)
            _require_version(card.version, expected_version)

            card.slug = body.slug
            card.display_name = body.display_name
            settings = _dict_value(card.settings)
            settings.update(
                {
                    "title": body.title,
                    "avatar_url": _url_value(body.avatar_url),
                    "assistant_name": body.assistant_name,
                    "welcome_message": body.welcome_message,
                    "suggested_questions": list(body.suggested_questions),
                    "policy_versions": dict(body.policy_versions),
                }
            )
            card.settings = settings
            card.version += 1
            await self._audit(
                session,
                scope=scope,
                action="card.update",
                resource_type="card",
                resource_id=card.id,
                trace_id=trace_id,
                event_data={"version": card.version, "slug": card.slug},
            )
            await session.flush()
            await session.refresh(card)
            return _card_profile(card)

    async def list_documents(
        self,
        *,
        scope: AdminScope,
        limit: int = 50,
        selectable_faq: bool = False,
    ) -> tuple[list[KnowledgeDocumentRecord | SelectableFaqRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = list(
                selectable_faq_filters(scope)
                if selectable_faq
                else (
                    KnowledgeDocument.tenant_id == scope.tenant_id,
                    KnowledgeDocument.company_id == scope.company_id,
                )
            )
            total = int(
                await session.scalar(select(func.count(KnowledgeDocument.id)).where(*filters)) or 0
            )
            documents = list(
                (
                    await session.scalars(
                        select(KnowledgeDocument)
                        .where(*filters)
                        .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id)
                        .limit(limit)
                    )
                ).all()
            )
            records = [
                await self._document_record(session, scope=scope, document=document)
                for document in documents
            ]
            if selectable_faq:
                answers = await self._selectable_faq_answers(
                    session,
                    scope=scope,
                    documents=documents,
                )
                records = [
                    SelectableFaqRecord.model_validate(
                        {
                            **record.model_dump(),
                            "visibility": "public",
                            "answer": answers.get(record.id, ""),
                        }
                    )
                    for record in records
                ]
            return records, total

    async def get_document_detail(
        self,
        *,
        scope: AdminScope,
        document_id: uuid.UUID,
    ) -> KnowledgeDocumentDetail:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document = await self._document(
                session,
                scope=scope,
                document_id=document_id,
            )
            record = await self._document_record(session, scope=scope, document=document)
            latest = await session.scalar(
                select(KnowledgeVersion)
                .where(
                    KnowledgeVersion.tenant_id == scope.tenant_id,
                    KnowledgeVersion.company_id == scope.company_id,
                    KnowledgeVersion.document_id == document.id,
                )
                .order_by(KnowledgeVersion.version_number.desc())
                .limit(1)
            )
            first_chunk = None
            if latest is not None:
                first_chunk = await session.scalar(
                    select(KnowledgeChunk)
                    .where(
                        KnowledgeChunk.tenant_id == scope.tenant_id,
                        KnowledgeChunk.company_id == scope.company_id,
                        KnowledgeChunk.document_id == document.id,
                        KnowledgeChunk.version_id == latest.id,
                    )
                    .order_by(KnowledgeChunk.ordinal)
                    .limit(1)
                )
            return KnowledgeDocumentDetail(
                **record.model_dump(),
                raw_text=latest.raw_text if latest is not None else None,
                visibility=first_chunk.visibility.value if first_chunk is not None else None,
                metadata=_dict_value(first_chunk.metadata_json) if first_chunk is not None else {},
                editable_version_id=latest.id if latest is not None else None,
            )

    async def create_document(
        self,
        *,
        scope: AdminScope,
        body: CreateKnowledgeDocumentRequest,
        trace_id: str | None = None,
    ) -> KnowledgeDocumentRecord:
        document_id = uuid.uuid4()
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document = KnowledgeDocument(
                id=document_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                source_type=body.source_type,
                source_id=body.source_id or f"admin:{document_id}",
                title=body.title,
                status=ContentStatus.DRAFT,
                version=1,
            )
            session.add(document)
            await session.flush()
            await self._audit(
                session,
                scope=scope,
                action="knowledge.document.create",
                resource_type="knowledge_document",
                resource_id=document.id,
                trace_id=trace_id,
                event_data={"source_type": document.source_type},
            )
            await session.flush()
            return await self._document_record(session, scope=scope, document=document)

    async def put_document_draft(
        self,
        *,
        scope: AdminScope,
        document_id: uuid.UUID,
        body: PutKnowledgeDocumentRequest,
        trace_id: str | None = None,
    ) -> KnowledgeDraftResult:
        raw_text = body.raw_text.strip()
        chunks = chunk_knowledge_text(raw_text)
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document = await self._document(
                session,
                scope=scope,
                document_id=document_id,
                for_update=True,
            )
            next_version = (
                int(
                    await session.scalar(
                        select(func.max(KnowledgeVersion.version_number)).where(
                            KnowledgeVersion.tenant_id == scope.tenant_id,
                            KnowledgeVersion.company_id == scope.company_id,
                            KnowledgeVersion.document_id == document.id,
                        )
                    )
                    or 0
                )
                + 1
            )
            await session.execute(
                update(KnowledgeVersion)
                .where(
                    KnowledgeVersion.tenant_id == scope.tenant_id,
                    KnowledgeVersion.company_id == scope.company_id,
                    KnowledgeVersion.document_id == document.id,
                    KnowledgeVersion.review_status == ReviewStatus.DRAFT,
                )
                .values(review_status=ReviewStatus.ARCHIVED)
            )

            version = KnowledgeVersion(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                document_id=document.id,
                version_number=next_version,
                raw_text=raw_text,
                content_hash=_sha256(raw_text),
                review_status=ReviewStatus.DRAFT,
            )
            session.add(version)
            await session.flush()

            title = body.title or document.title
            document.title = title
            if document.current_version_id is None:
                document.status = ContentStatus.DRAFT
            document.version += 1
            metadata = dict(body.metadata)
            chunk_rows = [
                KnowledgeChunk(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    document_id=document.id,
                    version_id=version.id,
                    ordinal=ordinal,
                    title=title,
                    text=chunk,
                    token_count=max(1, (len(chunk) + 1) // 2),
                    embedding=None,
                    embedding_model=None,
                    visibility=Visibility(body.visibility),
                    is_active=False,
                    source_type=document.source_type,
                    source_id=document.source_id,
                    content_hash=_sha256(chunk),
                    metadata_json=dict(metadata),
                )
                for ordinal, chunk in enumerate(chunks)
            ]
            session.add_all(chunk_rows)
            await session.flush()
            await self._audit(
                session,
                scope=scope,
                action="knowledge.version.create",
                resource_type="knowledge_version",
                resource_id=version.id,
                trace_id=trace_id,
                event_data={
                    "document_id": str(document.id),
                    "version_number": version.version_number,
                    "chunk_count": len(chunk_rows),
                },
            )
            await session.flush()
            await session.refresh(document)
            record = await self._document_record(session, scope=scope, document=document)
            summary = await self._version_summary(session, scope=scope, version=version)
            return KnowledgeDraftResult(document=record, draft_version=summary)

    async def publish_document(
        self,
        *,
        scope: AdminScope,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None = None,
        trace_id: str | None = None,
    ) -> KnowledgePublishResult:
        provider, credentials = self._embedding_runtime()
        prepared = await self._prepare_publish(
            scope=scope,
            document_id=document_id,
            version_id=version_id,
        )
        try:
            vectors: list[tuple[float, ...]] = []
            for start in range(0, len(prepared.chunks), _EMBEDDING_BATCH_SIZE):
                batch = prepared.chunks[start : start + _EMBEDDING_BATCH_SIZE]
                result = await provider.embed(
                    [as_passage(f"{chunk.title}\n{chunk.text}") for chunk in batch],
                    credentials=credentials,
                    trace_id=trace_id,
                )
                vectors.extend(
                    validate_embedding_vectors(
                        result.embeddings,
                        expected_count=len(batch),
                        expected_dimension=EMBEDDING_DIMENSION,
                    )
                )
            return await self._commit_publish(
                scope=scope,
                prepared=prepared,
                vectors=vectors,
                embedding_model=provider.model_name,
                trace_id=trace_id,
            )
        except asyncio.CancelledError:
            await self._safe_mark_job_failed(
                scope=scope,
                prepared=prepared,
                error_code="CANCELLED",
                error_detail="embedding publication was cancelled",
                trace_id=trace_id,
            )
            raise
        except Exception as exc:
            await self._safe_mark_job_failed(
                scope=scope,
                prepared=prepared,
                error_code=type(exc).__name__[:80],
                error_detail=str(exc)[:2_000],
                trace_id=trace_id,
            )
            if isinstance(exc, ApiError):
                raise
            raise ApiError(
                503,
                "EMBEDDING_FAILED",
                "知识向量生成失败，旧发布版本仍然有效",
            ) from exc

    async def _prepare_publish(
        self,
        *,
        scope: AdminScope,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None,
    ) -> PreparedPublish:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document = await self._document(
                session,
                scope=scope,
                document_id=document_id,
                for_update=True,
            )
            version_query = select(KnowledgeVersion).where(
                KnowledgeVersion.tenant_id == scope.tenant_id,
                KnowledgeVersion.company_id == scope.company_id,
                KnowledgeVersion.document_id == document.id,
                KnowledgeVersion.review_status == ReviewStatus.DRAFT,
            )
            if version_id is not None:
                version_query = version_query.where(KnowledgeVersion.id == version_id)
            else:
                version_query = version_query.order_by(
                    KnowledgeVersion.version_number.desc()
                ).limit(1)
            version = await session.scalar(version_query.with_for_update())
            if version is None:
                raise ApiError(409, "DRAFT_NOT_FOUND", "没有可发布的草稿版本")

            chunks = list(
                (
                    await session.scalars(
                        select(KnowledgeChunk)
                        .where(
                            KnowledgeChunk.tenant_id == scope.tenant_id,
                            KnowledgeChunk.company_id == scope.company_id,
                            KnowledgeChunk.document_id == document.id,
                            KnowledgeChunk.version_id == version.id,
                            KnowledgeChunk.is_active.is_(False),
                        )
                        .order_by(KnowledgeChunk.ordinal)
                        .with_for_update()
                    )
                ).all()
            )
            if not chunks:
                raise ApiError(409, "DRAFT_EMPTY", "草稿版本没有可索引内容")

            model_name = self._embedding_provider.model_name if self._embedding_provider else ""
            job = await session.scalar(
                select(KnowledgeIndexJob)
                .where(
                    KnowledgeIndexJob.tenant_id == scope.tenant_id,
                    KnowledgeIndexJob.company_id == scope.company_id,
                    KnowledgeIndexJob.version_id == version.id,
                    KnowledgeIndexJob.embedding_model == model_name,
                )
                .with_for_update()
            )
            now = datetime.now(UTC)
            if job is None:
                job = KnowledgeIndexJob(
                    id=uuid.uuid4(),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    version_id=version.id,
                    embedding_model=model_name,
                    status=IndexJobStatus.RUNNING,
                    attempt=1,
                    started_at=now,
                )
                session.add(job)
            else:
                job.status = IndexJobStatus.RUNNING
                job.attempt += 1
                job.error_code = None
                job.error_detail = None
                job.started_at = now
                job.completed_at = None
            await session.flush()
            return PreparedPublish(
                document_id=document.id,
                document_version=document.version,
                version_id=version.id,
                version_number=version.version_number,
                job_id=job.id,
                chunks=tuple(
                    PreparedChunk(
                        id=chunk.id,
                        title=chunk.title,
                        text=chunk.text,
                        content_hash=chunk.content_hash,
                    )
                    for chunk in chunks
                ),
            )

    async def _commit_publish(
        self,
        *,
        scope: AdminScope,
        prepared: PreparedPublish,
        vectors: Sequence[Sequence[float]],
        embedding_model: str,
        trace_id: str | None,
    ) -> KnowledgePublishResult:
        checked_vectors = validate_embedding_vectors(
            vectors,
            expected_count=len(prepared.chunks),
            expected_dimension=EMBEDDING_DIMENSION,
        )
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document = await self._document(
                session,
                scope=scope,
                document_id=prepared.document_id,
                for_update=True,
            )
            if document.version != prepared.document_version:
                raise ApiError(
                    409,
                    "VERSION_CONFLICT",
                    "知识文档已被其他操作更新，请刷新后重试",
                    details={"current_version": document.version},
                )
            version = await session.scalar(
                select(KnowledgeVersion)
                .where(
                    KnowledgeVersion.id == prepared.version_id,
                    KnowledgeVersion.tenant_id == scope.tenant_id,
                    KnowledgeVersion.company_id == scope.company_id,
                    KnowledgeVersion.document_id == document.id,
                )
                .with_for_update()
            )
            if version is None or version.review_status != ReviewStatus.DRAFT:
                raise ApiError(409, "VERSION_CONFLICT", "草稿版本状态已发生变化")
            chunks = list(
                (
                    await session.scalars(
                        select(KnowledgeChunk)
                        .where(
                            KnowledgeChunk.tenant_id == scope.tenant_id,
                            KnowledgeChunk.company_id == scope.company_id,
                            KnowledgeChunk.document_id == document.id,
                            KnowledgeChunk.version_id == version.id,
                        )
                        .order_by(KnowledgeChunk.ordinal)
                        .with_for_update()
                    )
                ).all()
            )
            expected_chunks = [(item.id, item.content_hash) for item in prepared.chunks]
            actual_chunks = [(item.id, item.content_hash) for item in chunks]
            if actual_chunks != expected_chunks:
                raise ApiError(409, "VERSION_CONFLICT", "草稿内容已发生变化")

            await session.execute(
                update(KnowledgeChunk)
                .where(
                    KnowledgeChunk.tenant_id == scope.tenant_id,
                    KnowledgeChunk.company_id == scope.company_id,
                    KnowledgeChunk.document_id == document.id,
                    KnowledgeChunk.is_active.is_(True),
                )
                .values(is_active=False)
            )
            for chunk, vector in zip(chunks, checked_vectors, strict=True):
                chunk.embedding = list(vector)
                chunk.embedding_model = embedding_model
                chunk.is_active = True

            now = datetime.now(UTC)
            version.review_status = ReviewStatus.APPROVED
            version.reviewed_by = scope.actor_user_id
            version.reviewed_at = now
            version.published_at = now

            # The database activation trigger validates the selected version at
            # document-update time. Persist approval and vectors first so the
            # trigger never observes an in-memory state that has not reached
            # PostgreSQL yet. The enclosing transaction keeps the switch atomic.
            await session.flush()

            document.current_version_id = version.id
            document.status = ContentStatus.PUBLISHED
            document.version += 1

            job = await session.scalar(
                select(KnowledgeIndexJob)
                .where(
                    KnowledgeIndexJob.id == prepared.job_id,
                    KnowledgeIndexJob.tenant_id == scope.tenant_id,
                    KnowledgeIndexJob.company_id == scope.company_id,
                    KnowledgeIndexJob.version_id == version.id,
                )
                .with_for_update()
            )
            if job is None:
                raise RuntimeError("knowledge index job disappeared during publication")
            job.status = IndexJobStatus.SUCCEEDED
            job.error_code = None
            job.error_detail = None
            job.completed_at = now
            await self._audit(
                session,
                scope=scope,
                action="knowledge.version.publish",
                resource_type="knowledge_version",
                resource_id=version.id,
                trace_id=trace_id,
                event_data={
                    "document_id": str(document.id),
                    "version_number": version.version_number,
                    "embedding_model": embedding_model,
                    "chunk_count": len(chunks),
                },
            )
            await session.flush()
            await session.refresh(document)
            record = await self._document_record(session, scope=scope, document=document)
            summary = await self._version_summary(session, scope=scope, version=version)
            return KnowledgePublishResult(
                document=record,
                published_version=summary,
                index_job_id=job.id,
                index_status=job.status.value,
            )

    async def _safe_mark_job_failed(
        self,
        *,
        scope: AdminScope,
        prepared: PreparedPublish,
        error_code: str,
        error_detail: str,
        trace_id: str | None,
    ) -> None:
        try:
            await self._mark_job_failed(
                scope=scope,
                prepared=prepared,
                error_code=error_code,
                error_detail=error_detail,
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.exception(
                "knowledge_index_job_failure_update_failed",
                error_type=type(exc).__name__,
                job_id=str(prepared.job_id),
            )

    async def _mark_job_failed(
        self,
        *,
        scope: AdminScope,
        prepared: PreparedPublish,
        error_code: str,
        error_detail: str,
        trace_id: str | None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            job = await session.scalar(
                select(KnowledgeIndexJob)
                .where(
                    KnowledgeIndexJob.id == prepared.job_id,
                    KnowledgeIndexJob.tenant_id == scope.tenant_id,
                    KnowledgeIndexJob.company_id == scope.company_id,
                    KnowledgeIndexJob.version_id == prepared.version_id,
                    KnowledgeIndexJob.status != IndexJobStatus.SUCCEEDED,
                )
                .with_for_update()
            )
            if job is None:
                return
            job.status = IndexJobStatus.FAILED
            job.error_code = error_code[:80]
            job.error_detail = error_detail[:2_000]
            job.completed_at = datetime.now(UTC)
            await self._audit(
                session,
                scope=scope,
                action="knowledge.version.publish_failed",
                resource_type="knowledge_version",
                resource_id=prepared.version_id,
                trace_id=trace_id,
                event_data={"job_id": str(job.id), "error_code": job.error_code},
            )

    def _embedding_runtime(self) -> tuple[EmbeddingProvider, ProviderCredentials]:
        if self._settings.embedding_dimension != EMBEDDING_DIMENSION:
            raise ApiError(
                503,
                "EMBEDDING_CONFIGURATION_INVALID",
                f"知识库要求 {EMBEDDING_DIMENSION} 维向量",
            )
        if self._embedding_provider is None or self._settings.embedding_api_key is None:
            raise ApiError(503, "EMBEDDING_UNAVAILABLE", "知识向量服务尚未配置")
        return self._embedding_provider, ProviderCredentials(
            self._settings.embedding_api_key.get_secret_value()
        )

    async def _set_scope(self, session: AsyncSession, scope: AdminScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    async def _company(
        self,
        session: AsyncSession,
        scope: AdminScope,
        *,
        for_update: bool = False,
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

    async def _card(
        self,
        session: AsyncSession,
        scope: AdminScope,
        *,
        for_update: bool = False,
    ) -> Card:
        statement = (
            select(Card)
            .where(
                Card.tenant_id == scope.tenant_id,
                Card.company_id == scope.company_id,
                Card.deleted_at.is_(None),
            )
            .order_by(Card.created_at, Card.id)
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update()
        card = await session.scalar(statement)
        if card is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "当前企业尚未创建名片")
        return card

    async def _document(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        document_id: uuid.UUID,
        for_update: bool = False,
    ) -> KnowledgeDocument:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == scope.tenant_id,
            KnowledgeDocument.company_id == scope.company_id,
        )
        if for_update:
            statement = statement.with_for_update()
        document = await session.scalar(statement)
        if document is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "知识文档不存在或不在当前作用域")
        return document

    async def _document_record(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        document: KnowledgeDocument,
    ) -> KnowledgeDocumentRecord:
        latest = await session.scalar(
            select(KnowledgeVersion)
            .where(
                KnowledgeVersion.tenant_id == scope.tenant_id,
                KnowledgeVersion.company_id == scope.company_id,
                KnowledgeVersion.document_id == document.id,
            )
            .order_by(KnowledgeVersion.version_number.desc())
            .limit(1)
        )
        current_version_number: int | None = None
        if document.current_version_id is not None:
            current_version_number = await session.scalar(
                select(KnowledgeVersion.version_number).where(
                    KnowledgeVersion.id == document.current_version_id,
                    KnowledgeVersion.tenant_id == scope.tenant_id,
                    KnowledgeVersion.company_id == scope.company_id,
                    KnowledgeVersion.document_id == document.id,
                )
            )
        latest_summary = (
            await self._version_summary(session, scope=scope, version=latest)
            if latest is not None
            else None
        )
        return KnowledgeDocumentRecord(
            id=document.id,
            source_type=document.source_type,
            source_id=document.source_id,
            title=document.title,
            status=document.status.value,
            version=document.version,
            current_version_id=document.current_version_id,
            current_version_number=current_version_number,
            latest_version=latest_summary,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    async def _selectable_faq_answers(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        documents: Sequence[KnowledgeDocument],
    ) -> dict[uuid.UUID, str]:
        document_ids = [document.id for document in documents]
        if not document_ids:
            return {}
        rows = (
            await session.execute(
                select(
                    KnowledgeDocument.id.label("document_id"),
                    KnowledgeChunk.text,
                )
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
                .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeChunk.ordinal)
            )
        ).all()
        answer_parts: dict[uuid.UUID, list[str]] = {}
        for row in rows:
            answer_parts.setdefault(uuid.UUID(str(row.document_id)), []).append(str(row.text))
        return {
            document_id: "\n\n".join(parts)
            for document_id, parts in answer_parts.items()
        }

    async def _version_summary(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        version: KnowledgeVersion,
    ) -> KnowledgeVersionSummary:
        filters = (
            KnowledgeChunk.tenant_id == scope.tenant_id,
            KnowledgeChunk.company_id == scope.company_id,
            KnowledgeChunk.document_id == version.document_id,
            KnowledgeChunk.version_id == version.id,
        )
        chunk_count = int(
            await session.scalar(select(func.count(KnowledgeChunk.id)).where(*filters)) or 0
        )
        indexed_chunk_count = int(
            await session.scalar(
                select(func.count(KnowledgeChunk.id)).where(
                    *filters,
                    KnowledgeChunk.embedding.is_not(None),
                )
            )
            or 0
        )
        index_job = await session.scalar(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.tenant_id == scope.tenant_id,
                KnowledgeIndexJob.company_id == scope.company_id,
                KnowledgeIndexJob.version_id == version.id,
            )
            .order_by(KnowledgeIndexJob.updated_at.desc(), KnowledgeIndexJob.id.desc())
            .limit(1)
        )
        return KnowledgeVersionSummary(
            id=version.id,
            version_number=version.version_number,
            review_status=version.review_status.value,
            chunk_count=chunk_count,
            indexed_chunk_count=indexed_chunk_count,
            index_status=index_job.status.value if index_job else None,
            index_error_code=index_job.error_code if index_job else None,
            published_at=version.published_at,
            created_at=version.created_at,
        )

    async def _audit(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
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


def chunk_knowledge_text(value: str, *, max_chars: int = _CHUNK_MAX_CHARS) -> tuple[str, ...]:
    normalized = value.strip()
    if not normalized:
        raise ValueError("knowledge text must not be blank")
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")

    paragraphs = [paragraph.strip() for paragraph in normalized.split("\n\n") if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        parts = [
            paragraph[index : index + max_chars] for index in range(0, len(paragraph), max_chars)
        ]
        for part in parts:
            candidate = f"{current}\n\n{part}" if current else part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = part
    if current:
        chunks.append(current)
    return tuple(chunks)


def as_passage(value: str) -> str:
    normalized = " ".join(value.split())
    if normalized.casefold().startswith("passage: "):
        return normalized
    return f"passage: {normalized}"


def validate_embedding_vectors(
    vectors: Sequence[Sequence[float]],
    *,
    expected_count: int,
    expected_dimension: int = EMBEDDING_DIMENSION,
) -> list[tuple[float, ...]]:
    if len(vectors) != expected_count:
        raise ValueError("embedding provider returned the wrong batch size")
    checked: list[tuple[float, ...]] = []
    for vector in vectors:
        values = tuple(float(value) for value in vector)
        if len(values) != expected_dimension or any(not math.isfinite(value) for value in values):
            raise ValueError("embedding provider returned an invalid vector")
        checked.append(values)
    return checked


def _company_profile(company: Company) -> CompanyProfile:
    settings = _dict_value(company.settings)
    policy_versions = _dict_value(settings.get("policy_versions"))
    return CompanyProfile(
        id=company.id,
        name=company.name,
        summary=_string_value(settings.get("summary")) or "",
        industry=company.industry,
        region=_string_value(settings.get("region")),
        website=_string_value(settings.get("website")),
        logo_url=_string_value(settings.get("logo_url")),
        profile_personalization_policy_version=(
            _string_value(policy_versions.get("profile_personalization"))
            or "profile-personalization-v1"
        ),
        status=company.status.value,
        version=company.version,
        updated_at=company.updated_at,
    )


def _card_profile(card: Card) -> CardProfile:
    settings = _dict_value(card.settings)
    questions = settings.get("suggested_questions")
    policies = settings.get("policy_versions")
    return CardProfile(
        id=card.id,
        card_kind=card.card_kind.value,
        owner_user_id=card.owner_user_id,
        slug=card.slug,
        display_name=card.display_name,
        title=_string_value(settings.get("title")) or card.display_name,
        avatar_url=_string_value(settings.get("avatar_url")),
        assistant_name=_string_value(settings.get("assistant_name")),
        welcome_message=_string_value(settings.get("welcome_message")),
        suggested_questions=(
            [str(item) for item in questions if isinstance(item, str)][:6]
            if isinstance(questions, list)
            else []
        ),
        policy_versions=(
            {str(key): str(value) for key, value in policies.items()}
            if isinstance(policies, dict)
            else {}
        ),
        status=card.status.value,
        published_at=card.published_at,
        version=card.version,
        updated_at=card.updated_at,
    )


def _require_version(current: int, expected: int) -> None:
    if current != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "资源已被其他操作更新，请刷新后重试",
            details={"current_version": current},
        )


def _dict_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _url_value(value: object) -> str | None:
    return str(value) if value is not None else None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "AdminScope",
    "AdminStore",
    "PreparedChunk",
    "PreparedPublish",
    "as_passage",
    "chunk_knowledge_text",
    "validate_embedding_vectors",
]
