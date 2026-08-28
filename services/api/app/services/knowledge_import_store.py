from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.knowledge_import_schemas import (
    KnowledgeImportBatchRecord,
    KnowledgeImportItemRecord,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import (
    Company,
    KnowledgeImportBatch,
    KnowledgeImportBatchStatus,
    KnowledgeImportItem,
    KnowledgeImportItemStatus,
)
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
            company = await session.scalar(
                select(Company)
                .where(
                    Company.tenant_id == scope.tenant_id,
                    Company.id == scope.company_id,
                )
                .with_for_update()
            )
            if company is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "企业不存在")
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
                company_name=company.name,
                created_at=datetime.now(UTC),
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

    async def retry_item(
        self,
        *,
        scope: KnowledgeImportScope,
        batch_id: uuid.UUID,
        item_id: uuid.UUID,
        expected_batch_version: int,
        trace_id: str | None,
    ) -> KnowledgeImportBatchRecord:
        """Requeue one failed file while preserving tenant scope and audit history."""

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
            if batch.version != expected_batch_version:
                raise ApiError(409, "VERSION_CONFLICT", "任务已发生变化，请刷新后重试")
            item = await session.scalar(
                select(KnowledgeImportItem)
                .where(
                    KnowledgeImportItem.id == item_id,
                    KnowledgeImportItem.batch_id == batch_id,
                    KnowledgeImportItem.tenant_id == scope.tenant_id,
                    KnowledgeImportItem.company_id == scope.company_id,
                )
                .with_for_update()
            )
            if item is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "知识导入文件不存在")
            if item.status not in {
                KnowledgeImportItemStatus.FAILED,
                KnowledgeImportItemStatus.DEAD_LETTER,
            }:
                raise ApiError(409, "IMPORT_RETRY_NOT_ALLOWED", "只有失败或已终止的文件可以重试")
            if item.payload_ciphertext is None:
                raise ApiError(
                    409,
                    "IMPORT_RETRY_PAYLOAD_UNAVAILABLE",
                    "该旧任务的原始文件已按历史策略清理，请重新上传此文件",
                )

            previous_error = item.error_code
            item.status = KnowledgeImportItemStatus.PENDING
            item.attempts = 0
            item.next_attempt_at = datetime.now(UTC)
            item.lock_token = None
            item.locked_by = None
            item.lease_expires_at = None
            item.error_code = None
            item.parse_status = "pending"
            item.publish_status = None
            item.completed_at = None
            item.published_at = None
            batch.version += 1
            await session.flush()
            await self._refresh_batch_counts(session, batch)
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge.import.retry",
                resource_type="knowledge_import_item",
                resource_id=item.id,
                trace_id=trace_id,
                event_data={
                    "batch_id": str(batch.id),
                    "previous_error_code": previous_error,
                },
            )
            await session.flush()
            return await self._record(session, scope, batch, with_items=True)

    async def clear_failed_item_payload(
        self,
        *,
        scope: KnowledgeImportScope,
        batch_id: uuid.UUID,
        item_id: uuid.UUID,
        expected_batch_version: int,
        trace_id: str | None,
    ) -> KnowledgeImportBatchRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            batch = await session.scalar(select(KnowledgeImportBatch).where(
                KnowledgeImportBatch.id == batch_id,
                KnowledgeImportBatch.tenant_id == scope.tenant_id,
                KnowledgeImportBatch.company_id == scope.company_id,
            ).with_for_update())
            if batch is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "知识导入批次不存在")
            if batch.version != expected_batch_version:
                raise ApiError(409, "VERSION_CONFLICT", "任务已发生变化，请刷新后重试")
            item = await session.scalar(select(KnowledgeImportItem).where(
                KnowledgeImportItem.id == item_id,
                KnowledgeImportItem.batch_id == batch_id,
                KnowledgeImportItem.tenant_id == scope.tenant_id,
                KnowledgeImportItem.company_id == scope.company_id,
            ).with_for_update())
            if item is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "知识导入文件不存在")
            if item.status not in {
                KnowledgeImportItemStatus.FAILED,
                KnowledgeImportItemStatus.DEAD_LETTER,
            }:
                raise ApiError(409, "IMPORT_CLEAR_NOT_ALLOWED", "只有失败或已终止文件可以清除")
            item.payload_ciphertext = None
            batch.version += 1
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="knowledge.import.clear_payload",
                resource_type="knowledge_import_item",
                resource_id=item.id,
                trace_id=trace_id,
                event_data={"batch_id": str(batch.id), "error_code": item.error_code},
            )
            await session.flush()
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
                    attempts=item.attempts,
                    max_attempts=item.max_attempts,
                    retry_available=(
                        item.status
                        in {
                            KnowledgeImportItemStatus.FAILED,
                            KnowledgeImportItemStatus.DEAD_LETTER,
                        }
                        and item.payload_ciphertext is not None
                    ),
                    created_at=item.created_at,
                    completed_at=item.completed_at,
                    published_at=item.published_at,
                )
                for item in rows
            ],
        )

    @staticmethod
    async def _refresh_batch_counts(
        session: AsyncSession, batch: KnowledgeImportBatch
    ) -> None:
        statuses = list(
            (
                await session.scalars(
                    select(KnowledgeImportItem.status).where(
                        KnowledgeImportItem.batch_id == batch.id,
                        KnowledgeImportItem.tenant_id == batch.tenant_id,
                        KnowledgeImportItem.company_id == batch.company_id,
                    )
                )
            ).all()
        )
        pending = sum(
            status
            in {
                KnowledgeImportItemStatus.PENDING,
                KnowledgeImportItemStatus.PROCESSING,
                KnowledgeImportItemStatus.FAILED,
            }
            for status in statuses
        )
        succeeded = sum(status == KnowledgeImportItemStatus.COMPLETED for status in statuses)
        failed = sum(status == KnowledgeImportItemStatus.DEAD_LETTER for status in statuses)
        batch.pending_items = pending
        batch.succeeded_items = succeeded
        batch.failed_items = failed
        batch.completed_at = None if pending else datetime.now(UTC)
        if pending and (succeeded or failed):
            batch.status = KnowledgeImportBatchStatus.PROCESSING
        elif pending:
            batch.status = KnowledgeImportBatchStatus.PENDING
        elif succeeded and not failed:
            batch.status = KnowledgeImportBatchStatus.COMPLETED
        elif succeeded and failed:
            batch.status = KnowledgeImportBatchStatus.COMPLETED_WITH_ERRORS
        else:
            batch.status = KnowledgeImportBatchStatus.DEAD_LETTER

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
    *,
    requested: str | None,
    company_name: str,
    created_at: datetime,
    sequence_number: int,
) -> str:
    if requested and requested.strip():
        return requested.strip()[:120]
    return (f"{company_name.strip()}·资料导入·{created_at:%Y-%m-%d}·第 {sequence_number} 次")[:120]
