from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.knowledge_import_schemas import (
    KnowledgeImportBatchRecord,
    KnowledgeImportItemRecord,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import Company, KnowledgeImportBatch, KnowledgeImportItem
from app.db.session import set_rls_context
from app.services.audit import append_audit


@dataclass(frozen=True, slots=True)
class KnowledgeImportScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class PendingImport:
    file_name: str
    source_type: str
    content_type: str
    payload: bytes


class KnowledgeImportStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = sessions
        self._cipher = PiiCipher.from_settings(settings)

    async def create_batch(
        self,
        *,
        scope: KnowledgeImportScope,
        items: list[PendingImport],
        auto_publish: bool,
        display_name: str | None,
        trace_id: str | None,
    ) -> KnowledgeImportBatchRecord:
        batch_id = uuid.uuid4()
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await session.scalar(
                select(Company.id)
                .where(
                    Company.tenant_id == scope.tenant_id,
                    Company.id == scope.company_id,
                )
                .with_for_update()
            )
            last_sequence = int(
                await session.scalar(
                    select(func.max(KnowledgeImportBatch.sequence_number)).where(
                        KnowledgeImportBatch.tenant_id == scope.tenant_id,
                        KnowledgeImportBatch.company_id == scope.company_id,
                    )
                )
                or 0
            )
            sequence_number = last_sequence + 1
            resolved_name = _batch_display_name(
                requested=display_name,
                items=items,
                sequence_number=sequence_number,
            )
            batch = KnowledgeImportBatch(
                id=batch_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                requested_by=scope.actor_user_id,
                sequence_number=sequence_number,
                display_name=resolved_name,
                auto_publish=auto_publish,
                total_items=len(items),
                pending_items=len(items),
                succeeded_items=0,
                failed_items=0,
            )
            session.add(batch)
            for item in items:
                plaintext = item.payload
                session.add(
                    KnowledgeImportItem(
                        id=uuid.uuid4(),
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                        batch_id=batch.id,
                        file_name=item.file_name,
                        source_type=item.source_type,
                        content_type=item.content_type,
                        row_number=None,
                        auto_publish=auto_publish,
                        payload_ciphertext=self._cipher.encrypt_bytes(plaintext),
                        payload_sha256=hashlib.sha256(plaintext).hexdigest(),
                        encryption_key_ref=self._cipher.key_ref,
                    )
                )
            await session.flush()
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge.import.request",
                resource_type="knowledge_import_batch",
                resource_id=batch.id,
                trace_id=trace_id,
                event_data={
                    "item_count": len(items),
                    "auto_publish": auto_publish,
                    "sequence_number": sequence_number,
                    "display_name": resolved_name,
                },
            )
            await session.flush()
            return await self._record(session, scope, batch, with_items=True)

    async def rename_batch(
        self,
        *,
        scope: KnowledgeImportScope,
        batch_id: uuid.UUID,
        display_name: str,
        expected_version: int,
        trace_id: str | None,
    ) -> KnowledgeImportBatchRecord:
        normalized = display_name.strip()
        if not normalized:
            raise ApiError(422, "IMPORT_BATCH_NAME_EMPTY", "任务名称不能为空")
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            batch = await session.scalar(
                select(KnowledgeImportBatch)
                .where(
                    KnowledgeImportBatch.id == batch_id,
                    KnowledgeImportBatch.tenant_id == scope.tenant_id,
                    KnowledgeImportBatch.company_id == scope.company_id,
                )
                .with_for_update()
            )
            if batch is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "知识导入批次不存在")
            if batch.version != expected_version:
                raise ApiError(409, "VERSION_CONFLICT", "任务已被其他人修改，请刷新后重试")
            previous = batch.display_name
            batch.display_name = normalized[:120]
            batch.version += 1
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge.import.rename",
                resource_type="knowledge_import_batch",
                resource_id=batch.id,
                trace_id=trace_id,
                event_data={"previous_name": previous, "display_name": batch.display_name},
            )
            await session.flush()
            return await self._record(session, scope, batch, with_items=True)

    async def get_batch(
        self, *, scope: KnowledgeImportScope, batch_id: uuid.UUID
    ) -> KnowledgeImportBatchRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            batch = await session.scalar(
                select(KnowledgeImportBatch).where(
                    KnowledgeImportBatch.id == batch_id,
                    KnowledgeImportBatch.tenant_id == scope.tenant_id,
                    KnowledgeImportBatch.company_id == scope.company_id,
                )
            )
            if batch is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "知识导入批次不存在")
            return await self._record(session, scope, batch, with_items=True)

    async def get_batches_by_ids(
        self,
        *,
        scope: KnowledgeImportScope,
        batch_ids: list[uuid.UUID],
    ) -> list[KnowledgeImportBatchRecord]:
        """Return only explicitly scoped batches, preserving the caller's order.

        Platform onboarding resolves ``scope`` and ``batch_ids`` from a
        protected onboarding session before calling this method.  Keeping both
        the company filters and the explicit id allow-list here prevents a
        platform progress poll from turning into a general cross-tenant import
        listing endpoint.
        """

        ordered_ids = list(dict.fromkeys(batch_ids))
        if not ordered_ids:
            return []
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            rows = (
                await session.scalars(
                    select(KnowledgeImportBatch).where(
                        KnowledgeImportBatch.tenant_id == scope.tenant_id,
                        KnowledgeImportBatch.company_id == scope.company_id,
                        KnowledgeImportBatch.id.in_(ordered_ids),
                    )
                )
            ).all()
            by_id = {row.id: row for row in rows}
            return [
                await self._record(session, scope, by_id[batch_id], with_items=True)
                for batch_id in ordered_ids
                if batch_id in by_id
            ]

    async def list_batches(
        self, *, scope: KnowledgeImportScope, limit: int, offset: int
    ) -> tuple[list[KnowledgeImportBatchRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = (
                KnowledgeImportBatch.tenant_id == scope.tenant_id,
                KnowledgeImportBatch.company_id == scope.company_id,
            )
            total = int(await session.scalar(select(func.count()).where(*filters)) or 0)
            batches = (
                await session.scalars(
                    select(KnowledgeImportBatch)
                    .where(*filters)
                    .order_by(
                        KnowledgeImportBatch.created_at.desc(), KnowledgeImportBatch.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            return [await self._record(session, scope, batch) for batch in batches], total

    async def _record(
        self,
        session: AsyncSession,
        scope: KnowledgeImportScope,
        batch: KnowledgeImportBatch,
        *,
        with_items: bool = False,
    ) -> KnowledgeImportBatchRecord:
        rows: list[KnowledgeImportItem] = []
        if with_items:
            rows = list(
                (
                    await session.scalars(
                        select(KnowledgeImportItem)
                        .where(
                            KnowledgeImportItem.tenant_id == scope.tenant_id,
                            KnowledgeImportItem.company_id == scope.company_id,
                            KnowledgeImportItem.batch_id == batch.id,
                        )
                        .order_by(KnowledgeImportItem.created_at, KnowledgeImportItem.id)
                    )
                ).all()
            )
        return KnowledgeImportBatchRecord(
            id=batch.id,
            sequence_number=batch.sequence_number,
            display_name=batch.display_name,
            version=batch.version,
            status=batch.status.value,
            auto_publish=batch.auto_publish,
            total_items=batch.total_items,
            pending_items=batch.pending_items,
            succeeded_items=batch.succeeded_items,
            failed_items=batch.failed_items,
            created_at=batch.created_at,
            completed_at=batch.completed_at,
            items=[
                KnowledgeImportItemRecord(
                    id=item.id,
                    file_name=item.file_name,
                    source_type=item.source_type,
                    status=item.status.value,
                    auto_publish=item.auto_publish,
                    parse_status=item.parse_status,
                    publish_status=item.publish_status,
                    row_number=item.row_number,
                    document_id=item.document_id,
                    version_id=item.version_id,
                    error_code=item.error_code,
                    created_at=item.created_at,
                    completed_at=item.completed_at,
                    published_at=item.published_at,
                )
                for item in rows
            ],
        )

    @staticmethod
    async def _set_scope(session: AsyncSession, scope: KnowledgeImportScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            actor_user_id=scope.actor_user_id,
        )


__all__ = ["KnowledgeImportScope", "KnowledgeImportStore", "PendingImport"]


def _batch_display_name(
    *, requested: str | None, items: list[PendingImport], sequence_number: int
) -> str:
    if requested and requested.strip():
        return requested.strip()[:120]
    first = items[0].file_name.rsplit(".", 1)[0].strip() if items else ""
    if first and len(items) == 1:
        return first[:120]
    if first:
        return f"{first}等 {len(items)} 份资料"[:120]
    return f"资料导入 #{sequence_number:03d}"
