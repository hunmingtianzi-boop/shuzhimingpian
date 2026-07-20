from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

import httpx
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.providers import (
    EmbeddingProviderConfig,
    HttpxJsonTransport,
    OpenAICompatibleEmbeddingProvider,
)
from app.ai.schemas import ProviderCredentials
from app.core.config import Settings, get_settings
from app.db.models import (
    ContentStatus,
    IndexJobStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndexJob,
    KnowledgeVersion,
    ReviewStatus,
)
from app.db.session import set_rls_context

_INDEX_NAMESPACE = uuid.UUID("be0ba3d5-1388-48cd-a779-fb67e47bb97f")
_RUNTIME_REVISION = "fastembed-0.8.0-mean-metadata-v2"


@dataclass(frozen=True, slots=True)
class Scope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class PreparedIndex:
    scope: Scope
    document_id: uuid.UUID
    source_version_id: uuid.UUID
    target_version_id: uuid.UUID
    job_id: uuid.UUID


def model_fingerprint(model: str, dimensions: int) -> str:
    return f"{model}|{dimensions}|{_RUNTIME_REVISION}"


def target_version_id(source_version_id: uuid.UUID, fingerprint: str) -> uuid.UUID:
    return uuid.uuid5(_INDEX_NAMESPACE, f"version:{source_version_id}:{fingerprint}")


def target_chunk_id(version_id: uuid.UUID, ordinal: int) -> uuid.UUID:
    return uuid.uuid5(_INDEX_NAMESPACE, f"chunk:{version_id}:{ordinal}")


def index_job_id(version_id: uuid.UUID, model: str) -> uuid.UUID:
    return uuid.uuid5(_INDEX_NAMESPACE, f"job:{version_id}:{model}")


def _content_signature(chunk: KnowledgeChunk) -> tuple[Any, ...]:
    return (
        chunk.ordinal,
        chunk.title,
        chunk.text,
        chunk.token_count,
        chunk.visibility.value,
        chunk.source_type,
        chunk.source_id,
        chunk.content_hash,
    )


def _has_target_embedding(chunk: KnowledgeChunk, *, model: str, dimensions: int) -> bool:
    return (
        chunk.embedding is not None
        and chunk.embedding_model == model
        and len(chunk.embedding) == dimensions
    )


def embedding_passage(
    *,
    title: str,
    content: str,
    metadata: Mapping[str, Any],
) -> str:
    """Include curated aliases and tags in semantic retrieval, not model evidence."""

    hints: list[str] = []
    for key in ("aliases", "tags"):
        values = metadata.get(key)
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str) and value.strip() and value.strip() not in hints:
                hints.append(value.strip())
    hint_text = f"\n检索提示：{'；'.join(hints)}" if hints else ""
    return f"passage: {title}{hint_text}\n{content.strip()}"


async def _discover_scopes(settings: Settings) -> list[Scope]:
    if not settings.migration_database_url:
        raise ValueError("MIGRATION_DATABASE_URL is required to discover indexing scopes")
    engine = create_async_engine(settings.migration_database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT DISTINCT tenant_id, company_id
                        FROM knowledge_documents
                        WHERE status = 'published' AND current_version_id IS NOT NULL
                        ORDER BY tenant_id, company_id
                        """
                    )
                )
            ).all()
        return [Scope(tenant_id=row.tenant_id, company_id=row.company_id) for row in rows]
    finally:
        await engine.dispose()


async def _document_ids(
    sessions: async_sessionmaker[AsyncSession], scope: Scope
) -> list[uuid.UUID]:
    async with sessions() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )
        return list(
            (
                await session.scalars(
                    select(KnowledgeDocument.id)
                    .where(
                        KnowledgeDocument.tenant_id == scope.tenant_id,
                        KnowledgeDocument.company_id == scope.company_id,
                        KnowledgeDocument.status == ContentStatus.PUBLISHED,
                        KnowledgeDocument.current_version_id.is_not(None),
                    )
                    .order_by(KnowledgeDocument.id)
                )
            ).all()
        )


async def _prepare_document(
    sessions: async_sessionmaker[AsyncSession],
    *,
    scope: Scope,
    document_id: uuid.UUID,
    model: str,
    dimensions: int,
    force: bool,
) -> PreparedIndex | None:
    fingerprint = model_fingerprint(model, dimensions)
    async with sessions() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )
        document = await session.scalar(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == scope.tenant_id,
                KnowledgeDocument.company_id == scope.company_id,
                KnowledgeDocument.status == ContentStatus.PUBLISHED,
            )
            .with_for_update()
        )
        if document is None or document.current_version_id is None:
            return None

        source = await session.scalar(
            select(KnowledgeVersion).where(
                KnowledgeVersion.id == document.current_version_id,
                KnowledgeVersion.document_id == document.id,
            )
        )
        if source is None or source.review_status != ReviewStatus.APPROVED:
            raise RuntimeError("published document does not have an approved source version")

        source_chunks = list(
            (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(
                        KnowledgeChunk.document_id == document.id,
                        KnowledgeChunk.version_id == source.id,
                    )
                    .order_by(KnowledgeChunk.ordinal)
                )
            ).all()
        )
        if not source_chunks:
            raise RuntimeError("published document has no source chunks")
        if not force and all(
            _has_target_embedding(chunk, model=model, dimensions=dimensions)
            for chunk in source_chunks
        ):
            return None

        target_id = target_version_id(source.id, fingerprint)
        target = await session.get(KnowledgeVersion, target_id)
        if target is None:
            next_version = (
                await session.scalar(
                    select(func.coalesce(func.max(KnowledgeVersion.version_number), 0) + 1)
                    .where(KnowledgeVersion.document_id == document.id)
                )
            )
            target = KnowledgeVersion(
                id=target_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                document_id=document.id,
                version_number=int(next_version or 1),
                raw_text=source.raw_text,
                content_hash=source.content_hash,
                review_status=ReviewStatus.REVIEW_PENDING,
                reviewed_by=None,
                reviewed_at=None,
                published_at=None,
            )
            session.add(target)
            await session.flush()

        if target.document_id != document.id or target.content_hash != source.content_hash:
            raise RuntimeError("deterministic target version conflicts with source content")

        existing_ordinals = set(
            (
                await session.scalars(
                    select(KnowledgeChunk.ordinal).where(KnowledgeChunk.version_id == target_id)
                )
            ).all()
        )
        for chunk in source_chunks:
            if chunk.ordinal in existing_ordinals:
                continue
            metadata = dict(chunk.metadata_json)
            metadata["embedding_index"] = {
                "source_version_id": str(source.id),
                "model": model,
                "dimensions": dimensions,
                "runtime_revision": _RUNTIME_REVISION,
            }
            session.add(
                KnowledgeChunk(
                    id=target_chunk_id(target_id, chunk.ordinal),
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    document_id=document.id,
                    version_id=target_id,
                    ordinal=chunk.ordinal,
                    title=chunk.title,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    embedding=None,
                    embedding_model=None,
                    visibility=chunk.visibility,
                    is_active=False,
                    source_type=chunk.source_type,
                    source_id=chunk.source_id,
                    content_hash=chunk.content_hash,
                    metadata_json=metadata,
                )
            )
        await session.flush()

        job_id = index_job_id(target_id, model)
        job = await session.scalar(
            select(KnowledgeIndexJob)
            .where(
                KnowledgeIndexJob.version_id == target_id,
                KnowledgeIndexJob.embedding_model == model,
            )
            .with_for_update()
        )
        if job is None:
            job = KnowledgeIndexJob(
                id=job_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                version_id=target_id,
                embedding_model=model,
                status=IndexJobStatus.RUNNING,
                attempt=1,
                started_at=datetime.now(UTC),
            )
            session.add(job)
        else:
            job.status = IndexJobStatus.RUNNING
            job.attempt += 1
            job.started_at = datetime.now(UTC)
            job.completed_at = None
            job.error_code = None
            job.error_detail = None

        return PreparedIndex(
            scope=scope,
            document_id=document.id,
            source_version_id=source.id,
            target_version_id=target_id,
            job_id=job.id,
        )


async def _embed_target(
    sessions: async_sessionmaker[AsyncSession],
    *,
    prepared: PreparedIndex,
    provider: OpenAICompatibleEmbeddingProvider,
    credentials: ProviderCredentials,
    model: str,
    dimensions: int,
) -> None:
    async with sessions() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=prepared.scope.tenant_id,
            company_id=prepared.scope.company_id,
        )
        chunks = list(
            (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.version_id == prepared.target_version_id)
                    .order_by(KnowledgeChunk.ordinal)
                )
            ).all()
        )

    missing = [
        chunk
        for chunk in chunks
        if not _has_target_embedding(chunk, model=model, dimensions=dimensions)
    ]
    for offset in range(0, len(missing), 16):
        batch_chunks = missing[offset : offset + 16]
        batch = await provider.embed(
            [
                embedding_passage(
                    title=chunk.title,
                    content=chunk.text,
                    metadata=chunk.metadata_json,
                )
                for chunk in batch_chunks
            ],
            credentials=credentials,
            trace_id=str(uuid.uuid4()),
        )
        if len(batch.embeddings) != len(batch_chunks):
            raise RuntimeError("embedding provider returned the wrong batch size")

        async with sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=prepared.scope.tenant_id,
                company_id=prepared.scope.company_id,
            )
            for chunk, embedding in zip(batch_chunks, batch.embeddings, strict=True):
                result = await session.execute(
                    update(KnowledgeChunk)
                    .where(
                        KnowledgeChunk.id == chunk.id,
                        KnowledgeChunk.version_id == prepared.target_version_id,
                        KnowledgeChunk.content_hash == chunk.content_hash,
                        KnowledgeChunk.is_active.is_(False),
                    )
                    .values(embedding=list(embedding), embedding_model=model)
                )
                if result.rowcount != 1:
                    raise RuntimeError("inactive target chunk changed during embedding write")


async def _finalize_document(
    sessions: async_sessionmaker[AsyncSession],
    *,
    prepared: PreparedIndex,
    model: str,
    dimensions: int,
) -> None:
    async with sessions() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=prepared.scope.tenant_id,
            company_id=prepared.scope.company_id,
        )
        document = await session.scalar(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == prepared.document_id)
            .with_for_update()
        )
        if document is None:
            raise RuntimeError("document disappeared during embedding indexing")
        if document.current_version_id == prepared.target_version_id:
            job = await session.get(KnowledgeIndexJob, prepared.job_id)
            if job is not None:
                job.status = IndexJobStatus.SUCCEEDED
                job.completed_at = datetime.now(UTC)
            return
        if document.current_version_id != prepared.source_version_id:
            raise RuntimeError("source version changed during embedding indexing")

        source = await session.get(KnowledgeVersion, prepared.source_version_id)
        target = await session.get(KnowledgeVersion, prepared.target_version_id)
        if source is None or target is None:
            raise RuntimeError("source or target version is missing")
        source_chunks = list(
            (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.version_id == source.id)
                    .order_by(KnowledgeChunk.ordinal)
                )
            ).all()
        )
        target_chunks = list(
            (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.version_id == target.id)
                    .order_by(KnowledgeChunk.ordinal)
                )
            ).all()
        )
        if [_content_signature(chunk) for chunk in source_chunks] != [
            _content_signature(chunk) for chunk in target_chunks
        ]:
            raise RuntimeError("target chunk content does not match the approved source")
        if not target_chunks or not all(
            _has_target_embedding(chunk, model=model, dimensions=dimensions)
            and not chunk.is_active
            for chunk in target_chunks
        ):
            raise RuntimeError("target embedding coverage is incomplete")
        if source.review_status != ReviewStatus.APPROVED or source.reviewed_by is None:
            raise RuntimeError("source approval cannot be carried forward")

        target.review_status = ReviewStatus.APPROVED
        target.reviewed_by = source.reviewed_by
        target.reviewed_at = source.reviewed_at
        target.published_at = datetime.now(UTC)
        await session.flush()

        document.current_version_id = target.id
        document.version += 1
        await session.flush()

        job = await session.get(KnowledgeIndexJob, prepared.job_id)
        if job is None:
            raise RuntimeError("embedding index job disappeared")
        job.status = IndexJobStatus.SUCCEEDED
        job.completed_at = datetime.now(UTC)
        job.error_code = None
        job.error_detail = None


async def _mark_failed(
    sessions: async_sessionmaker[AsyncSession],
    *,
    prepared: PreparedIndex,
    error: Exception,
) -> None:
    async with sessions() as session, session.begin():
        await set_rls_context(
            session,
            tenant_id=prepared.scope.tenant_id,
            company_id=prepared.scope.company_id,
        )
        job = await session.get(KnowledgeIndexJob, prepared.job_id)
        if job is not None:
            job.status = IndexJobStatus.FAILED
            job.completed_at = datetime.now(UTC)
            job.error_code = type(error).__name__[:80]
            job.error_detail = "Embedding indexing failed; inspect operator logs by job id."


async def index_all(*, settings: Settings, force: bool = False) -> None:
    if not (
        settings.embedding_provider
        and settings.embedding_base_url
        and settings.embedding_model
        and settings.embedding_api_key
    ):
        raise ValueError("embedding provider configuration is incomplete")

    scopes = await _discover_scopes(settings)
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    credentials = ProviderCredentials(settings.embedding_api_key.get_secret_value())
    failures: list[tuple[uuid.UUID, str]] = []
    async with httpx.AsyncClient(trust_env=False) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            EmbeddingProviderConfig(
                base_url=settings.embedding_base_url,
                model=settings.embedding_model,
                provider_name=settings.embedding_provider,
                timeout_seconds=settings.embedding_timeout_seconds,
                dimensions=settings.embedding_dimension,
                max_batch_size=64,
            ),
            transport=HttpxJsonTransport(client),
        )
        try:
            for scope in scopes:
                for document_id in await _document_ids(sessions, scope):
                    prepared = await _prepare_document(
                        sessions,
                        scope=scope,
                        document_id=document_id,
                        model=settings.embedding_model,
                        dimensions=settings.embedding_dimension,
                        force=force,
                    )
                    if prepared is None:
                        print(f"vector-ready {document_id}")
                        continue
                    try:
                        await _embed_target(
                            sessions,
                            prepared=prepared,
                            provider=provider,
                            credentials=credentials,
                            model=settings.embedding_model,
                            dimensions=settings.embedding_dimension,
                        )
                        await _finalize_document(
                            sessions,
                            prepared=prepared,
                            model=settings.embedding_model,
                            dimensions=settings.embedding_dimension,
                        )
                        print(f"indexed {document_id} -> {prepared.target_version_id}")
                    except Exception as exc:
                        await _mark_failed(sessions, prepared=prepared, error=exc)
                        failures.append((document_id, type(exc).__name__))
                        print(f"failed {document_id}: {type(exc).__name__}")
        finally:
            await engine.dispose()

    if failures:
        raise RuntimeError(f"embedding indexing failed for {len(failures)} document(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and atomically activate knowledge vectors")
    parser.add_argument(
        "--force",
        action="store_true",
        help="reindex even if current vectors match",
    )
    args = parser.parse_args()
    asyncio.run(index_all(settings=get_settings(), force=args.force))


if __name__ == "__main__":
    main()
