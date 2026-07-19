from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.knowledge_ops_schemas import (
    EvaluationJob,
    FaqRecord,
    KnowledgeChunkRecord,
    KnowledgeIndexJobRecord,
    KnowledgeVersionRecord,
)
from app.core.redaction import redact_sensitive_text
from app.db.models import (
    ContentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeIndexJob,
    KnowledgeVersion,
    OutboxEvent,
    OutboxStatus,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit


@dataclass(frozen=True, slots=True)
class KnowledgeOpsScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class IndexRetryTarget:
    job_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID


class KnowledgeOpsStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def list_faqs(
        self,
        *,
        scope: KnowledgeOpsScope,
        limit: int,
        offset: int,
    ) -> tuple[list[FaqRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = (
                KnowledgeDocument.tenant_id == scope.tenant_id,
                KnowledgeDocument.company_id == scope.company_id,
                KnowledgeDocument.source_type == "faq",
                KnowledgeDocument.status != ContentStatus.ARCHIVED,
            )
            total = int(
                await session.scalar(select(func.count(KnowledgeDocument.id)).where(*filters)) or 0
            )
            documents = (
                await session.scalars(
                    select(KnowledgeDocument)
                    .where(*filters)
                    .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [await self._faq_record(session, item) for item in documents], total

    async def get_faq(
        self,
        *,
        scope: KnowledgeOpsScope,
        document_id: uuid.UUID,
    ) -> FaqRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document = await self._faq_document(session, scope=scope, document_id=document_id)
            return await self._faq_record(session, document)

    async def archive_faq(
        self,
        *,
        scope: KnowledgeOpsScope,
        document_id: uuid.UUID,
        trace_id: str | None,
    ) -> FaqRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document = await self._faq_document(
                session,
                scope=scope,
                document_id=document_id,
                for_update=True,
            )
            document.status = ContentStatus.ARCHIVED
            document.version += 1
            await session.execute(
                update(KnowledgeChunk)
                .where(
                    KnowledgeChunk.tenant_id == scope.tenant_id,
                    KnowledgeChunk.company_id == scope.company_id,
                    KnowledgeChunk.document_id == document.id,
                )
                .values(is_active=False)
            )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="faq.archive",
                resource_type="knowledge_document",
                resource_id=document.id,
                trace_id=trace_id,
                event_data={},
            )
            await session.flush()
            await session.refresh(document)
            return await self._faq_record(session, document)

    async def list_versions(
        self,
        *,
        scope: KnowledgeOpsScope,
        document_id: uuid.UUID,
    ) -> list[KnowledgeVersionRecord]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._document(session, scope=scope, document_id=document_id)
            versions = (
                await session.scalars(
                    select(KnowledgeVersion)
                    .where(KnowledgeVersion.document_id == document_id)
                    .order_by(KnowledgeVersion.version_number.desc())
                )
            ).all()
            records = []
            for version in versions:
                total, indexed = (
                    await session.execute(
                        select(
                            func.count(KnowledgeChunk.id),
                            func.count(KnowledgeChunk.embedding),
                        ).where(KnowledgeChunk.version_id == version.id)
                    )
                ).one()
                visibility = await self._version_visibility(session, version.id)
                records.append(
                    KnowledgeVersionRecord(
                        id=version.id,
                        document_id=version.document_id,
                        version_number=version.version_number,
                        review_status=version.review_status.value,
                        visibility=visibility,
                        chunk_count=int(total or 0),
                        indexed_chunk_count=int(indexed or 0),
                        content_hash=version.content_hash,
                        published_at=version.published_at,
                        created_at=version.created_at,
                    )
                )
            return records

    async def version_document(
        self,
        *,
        scope: KnowledgeOpsScope,
        version_id: uuid.UUID,
    ) -> uuid.UUID:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            document_id = await session.scalar(
                select(KnowledgeVersion.document_id).where(
                    KnowledgeVersion.id == version_id,
                    KnowledgeVersion.tenant_id == scope.tenant_id,
                    KnowledgeVersion.company_id == scope.company_id,
                )
            )
            if document_id is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "知识版本不存在")
            return document_id

    async def list_index_jobs(
        self,
        *,
        scope: KnowledgeOpsScope,
        limit: int,
        offset: int,
        status: str | None,
    ) -> tuple[list[KnowledgeIndexJobRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [
                KnowledgeIndexJob.tenant_id == scope.tenant_id,
                KnowledgeIndexJob.company_id == scope.company_id,
            ]
            if status:
                filters.append(KnowledgeIndexJob.status == status)
            total = int(
                await session.scalar(select(func.count(KnowledgeIndexJob.id)).where(*filters)) or 0
            )
            rows = (
                await session.execute(
                    select(KnowledgeIndexJob, KnowledgeVersion, KnowledgeDocument)
                    .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeIndexJob.version_id)
                    .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
                    .where(*filters)
                    .order_by(
                        KnowledgeIndexJob.created_at.desc(),
                        KnowledgeIndexJob.id.desc(),
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [
                self._job_record(job, version, document) for job, version, document in rows
            ], total

    async def retry_target(
        self,
        *,
        scope: KnowledgeOpsScope,
        job_id: uuid.UUID,
    ) -> IndexRetryTarget:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            row = (
                await session.execute(
                    select(KnowledgeIndexJob, KnowledgeVersion)
                    .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeIndexJob.version_id)
                    .where(
                        KnowledgeIndexJob.id == job_id,
                        KnowledgeIndexJob.tenant_id == scope.tenant_id,
                        KnowledgeIndexJob.company_id == scope.company_id,
                    )
                )
            ).one_or_none()
            if row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "索引任务不存在")
            job, version = row
            if job.status.value != "failed":
                raise ApiError(409, "INDEX_JOB_NOT_RETRYABLE", "只有失败的索引任务可以重试")
            return IndexRetryTarget(job.id, version.document_id, version.id)

    async def get_index_job(
        self,
        *,
        scope: KnowledgeOpsScope,
        job_id: uuid.UUID,
    ) -> KnowledgeIndexJobRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            row = (
                await session.execute(
                    select(KnowledgeIndexJob, KnowledgeVersion, KnowledgeDocument)
                    .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeIndexJob.version_id)
                    .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeVersion.document_id)
                    .where(
                        KnowledgeIndexJob.id == job_id,
                        KnowledgeIndexJob.tenant_id == scope.tenant_id,
                        KnowledgeIndexJob.company_id == scope.company_id,
                    )
                )
            ).one_or_none()
            if row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "索引任务不存在")
            return self._job_record(*row)

    async def list_chunks(
        self,
        *,
        scope: KnowledgeOpsScope,
        limit: int,
        offset: int,
        document_id: uuid.UUID | None,
    ) -> tuple[list[KnowledgeChunkRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = [
                KnowledgeChunk.tenant_id == scope.tenant_id,
                KnowledgeChunk.company_id == scope.company_id,
            ]
            if document_id:
                filters.append(KnowledgeChunk.document_id == document_id)
            total = int(
                await session.scalar(select(func.count(KnowledgeChunk.id)).where(*filters)) or 0
            )
            chunks = (
                await session.scalars(
                    select(KnowledgeChunk)
                    .where(*filters)
                    .order_by(
                        KnowledgeChunk.created_at.desc(),
                        KnowledgeChunk.document_id,
                        KnowledgeChunk.ordinal,
                    )
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [
                KnowledgeChunkRecord(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    version_id=chunk.version_id,
                    ordinal=chunk.ordinal,
                    title=chunk.title,
                    text_preview=redact_sensitive_text(
                        " ".join(chunk.text.split())[:500]
                    ).content,
                    visibility=chunk.visibility.value,
                    is_active=chunk.is_active,
                    embedding_model=chunk.embedding_model,
                    source_type=chunk.source_type,
                    source_id=chunk.source_id,
                    metadata=_safe_chunk_metadata(chunk.metadata_json),
                )
                for chunk in chunks
            ], total

    async def enqueue_evaluation(
        self,
        *,
        scope: KnowledgeOpsScope,
        trace_id: str | None,
    ) -> EvaluationJob:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            job_id = uuid.uuid4()
            now = datetime.now(UTC)
            session.add(
                OutboxEvent(
                    id=job_id,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    aggregate_type="company",
                    aggregate_id=scope.company_id,
                    event_type="knowledge.evaluate.requested.v1",
                    payload={
                        "company_id": str(scope.company_id),
                        "requested_by": str(scope.actor_user_id),
                    },
                    headers={"trace_id": trace_id or ""},
                    deduplication_key=f"knowledge.evaluate:{job_id}",
                    status=OutboxStatus.PENDING,
                )
            )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge.evaluate.request",
                resource_type="evaluation_job",
                resource_id=job_id,
                trace_id=trace_id,
                event_data={},
            )
            return EvaluationJob(id=job_id, created_at=now)

    async def _faq_document(
        self,
        session: AsyncSession,
        *,
        scope: KnowledgeOpsScope,
        document_id: uuid.UUID,
        for_update: bool = False,
    ) -> KnowledgeDocument:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.tenant_id == scope.tenant_id,
            KnowledgeDocument.company_id == scope.company_id,
            KnowledgeDocument.source_type == "faq",
        )
        if for_update:
            statement = statement.with_for_update()
        document = await session.scalar(statement)
        if document is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "FAQ 不存在")
        return document

    async def _document(
        self,
        session: AsyncSession,
        *,
        scope: KnowledgeOpsScope,
        document_id: uuid.UUID,
    ) -> KnowledgeDocument:
        document = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == scope.tenant_id,
                KnowledgeDocument.company_id == scope.company_id,
            )
        )
        if document is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "知识文档不存在")
        return document

    async def _faq_record(self, session: AsyncSession, document: KnowledgeDocument) -> FaqRecord:
        version = await session.scalar(
            select(KnowledgeVersion)
            .where(KnowledgeVersion.document_id == document.id)
            .order_by(KnowledgeVersion.version_number.desc())
            .limit(1)
        )
        visibility = (
            await self._version_visibility(session, version.id) if version is not None else None
        )
        return FaqRecord(
            id=document.id,
            source_id=document.source_id,
            question=document.title,
            answer=version.raw_text if version else None,
            visibility=visibility,
            status=document.status.value,
            version=document.version,
            current_version_id=document.current_version_id,
            editable_version_id=(
                version.id
                if version is not None and version.review_status.value == "draft"
                else None
            ),
            created_at=document.created_at,
            updated_at=document.updated_at,
        )

    @staticmethod
    async def _version_visibility(session: AsyncSession, version_id: uuid.UUID) -> str:
        visibility = await session.scalar(
            select(KnowledgeChunk.visibility)
            .where(KnowledgeChunk.version_id == version_id)
            .order_by(KnowledgeChunk.ordinal)
            .limit(1)
        )
        # A draft version normally has at least one chunk. Keeping the public
        # default here matches the database column default for legacy/empty rows.
        return visibility.value if visibility is not None else "public"

    @staticmethod
    def _job_record(
        job: KnowledgeIndexJob,
        version: KnowledgeVersion,
        document: KnowledgeDocument,
    ) -> KnowledgeIndexJobRecord:
        return KnowledgeIndexJobRecord(
            id=job.id,
            document_id=document.id,
            document_title=document.title,
            version_id=version.id,
            embedding_model=job.embedding_model,
            status=job.status.value,
            attempt=job.attempt,
            error_code=job.error_code,
            error_detail=job.error_detail[:500] if job.error_detail else None,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def _set_scope(self, session: AsyncSession, scope: KnowledgeOpsScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

def _safe_chunk_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    allowed = {"source_label", "content_type", "published_at", "authoritative"}
    return {str(key): item for key, item in value.items() if key in allowed}


__all__ = ["IndexRetryTarget", "KnowledgeOpsScope", "KnowledgeOpsStore"]
