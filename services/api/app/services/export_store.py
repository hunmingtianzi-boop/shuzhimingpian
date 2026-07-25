from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.export_schemas import ExportAvailabilityView, ExportRequestView
from app.core.config import Settings
from app.core.pii import PiiCipher, PiiCipherError
from app.db.models import (
    Card,
    Conversation,
    DataExportRequest,
    DataExportStatus,
    DataExportType,
    Lead,
    OutboxEvent,
    OutboxStatus,
    Visit,
    Visitor,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit
from app.services.public_store import PublicStore, canonical_request_hash

ExportType = Literal["visitors", "leads", "conversations"]


@dataclass(frozen=True, slots=True)
class ExportScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    role: str

    @property
    def is_card_owner(self) -> bool:
        return self.role == "card_owner"


@dataclass(frozen=True, slots=True)
class ExportDownload:
    content: bytes
    file_name: str
    content_type: str


class ExportStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._cipher = PiiCipher.from_settings(settings)

    async def create(
        self,
        *,
        scope: ExportScope,
        export_type: ExportType,
        include_sensitive: bool,
        idempotency_key: str,
        trace_id: str | None,
    ) -> ExportRequestView:
        if include_sensitive and scope.is_card_owner:
            raise ApiError(
                403,
                "EXPORT_SENSITIVE_FORBIDDEN",
                "Only company administrators can export unmasked personal data.",
            )
        request_hash = canonical_request_hash(
            "create_data_export",
            {
                "actor_user_id": str(scope.actor_user_id),
                "export_type": export_type,
                "include_sensitive": include_sensitive,
            },
        )
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            claim = await PublicStore._claim_idempotency(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                scope=f"admin_export:{scope.actor_user_id}",
                key=idempotency_key,
                request_hash=request_hash,
            )
            if claim.replay:
                export_id = claim.record.resource_id
                if export_id is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "Stored export is unavailable.")
                record = await self._record(session, scope=scope, export_id=export_id)
                return self._view(record)

            export_id = uuid.uuid4()
            event_id = uuid.uuid4()
            scope_kind = "card_owner" if scope.is_card_owner else "company"
            event = OutboxEvent(
                id=event_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                aggregate_type="data_export",
                aggregate_id=export_id,
                aggregate_version=1,
                event_type="data_export.requested.v1",
                payload={"export_id": str(export_id), "requested_by": str(scope.actor_user_id)},
                headers={"contains_pii": False, "trace_id": trace_id},
                deduplication_key=f"data-export:{export_id}",
                status=OutboxStatus.PENDING,
            )
            record = DataExportRequest(
                id=export_id,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                requested_by=scope.actor_user_id,
                requested_role=scope.role,
                export_type=DataExportType(export_type),
                status=DataExportStatus.PENDING,
                scope_kind=scope_kind,
                owner_user_id=scope.actor_user_id if scope.is_card_owner else None,
                include_sensitive=include_sensitive,
                outbox_event_id=event_id,
            )
            session.add_all((event, record))
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="data_export.requested",
                resource_type="data_export",
                resource_id=export_id,
                trace_id=trace_id,
                event_data={
                    "export_type": export_type,
                    "include_sensitive": include_sensitive,
                    "scope_kind": scope_kind,
                },
            )
            PublicStore._complete_idempotency(
                claim.record,
                resource_type="data_export",
                resource_id=export_id,
                status_code=202,
                response_body={"id": str(export_id)},
            )
            await session.flush()
            await session.refresh(record)
            return self._view(record)

    async def list(
        self,
        *,
        scope: ExportScope,
        limit: int,
        offset: int,
    ) -> tuple[list[ExportRequestView], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = self._access_filters(scope)
            await self._expire_due(session, filters=filters)
            total = int(
                await session.scalar(
                    select(func.count(DataExportRequest.id)).where(*filters)
                )
                or 0
            )
            records = (
                await session.scalars(
                    select(DataExportRequest)
                    .where(*filters)
                    .order_by(DataExportRequest.created_at.desc(), DataExportRequest.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [self._view(record) for record in records], total

    async def availability(self, *, scope: ExportScope) -> ExportAvailabilityView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            owner_filter = (
                (Card.owner_user_id == scope.actor_user_id,)
                if scope.is_card_owner
                else ()
            )
            visitors = int(
                await session.scalar(
                    select(func.count(func.distinct(Visitor.id)))
                    .select_from(Visitor)
                    .join(
                        Visit,
                        (Visit.tenant_id == Visitor.tenant_id)
                        & (Visit.company_id == Visitor.company_id)
                        & (Visit.visitor_id == Visitor.id),
                    )
                    .join(
                        Card,
                        (Card.tenant_id == Visit.tenant_id)
                        & (Card.company_id == Visit.company_id)
                        & (Card.id == Visit.card_id),
                    )
                    .where(
                        Visitor.tenant_id == scope.tenant_id,
                        Visitor.company_id == scope.company_id,
                        *owner_filter,
                    )
                )
                or 0
            )
            leads = int(
                await session.scalar(
                    select(func.count(Lead.id))
                    .select_from(Lead)
                    .join(
                        Card,
                        (Card.tenant_id == Lead.tenant_id)
                        & (Card.company_id == Lead.company_id)
                        & (Card.id == Lead.card_id),
                    )
                    .where(
                        Lead.tenant_id == scope.tenant_id,
                        Lead.company_id == scope.company_id,
                        *owner_filter,
                    )
                )
                or 0
            )
            conversations = int(
                await session.scalar(
                    select(func.count(Conversation.id))
                    .select_from(Conversation)
                    .join(
                        Card,
                        (Card.tenant_id == Conversation.tenant_id)
                        & (Card.company_id == Conversation.company_id)
                        & (Card.id == Conversation.card_id),
                    )
                    .where(
                        Conversation.tenant_id == scope.tenant_id,
                        Conversation.company_id == scope.company_id,
                        *owner_filter,
                    )
                )
                or 0
            )
            return ExportAvailabilityView(
                visitors=visitors,
                leads=leads,
                conversations=conversations,
                generated_at=datetime.now(UTC),
            )

    async def get(
        self,
        *,
        scope: ExportScope,
        export_id: uuid.UUID,
    ) -> ExportRequestView:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            record = await self._record(session, scope=scope, export_id=export_id)
            self._expire_record(record)
            return self._view(record)

    async def download(
        self,
        *,
        scope: ExportScope,
        export_id: uuid.UUID,
        trace_id: str | None,
    ) -> ExportDownload:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            record = await self._record(session, scope=scope, export_id=export_id)
            self._expire_record(record)
            if record.status == DataExportStatus.EXPIRED:
                raise ApiError(410, "EXPORT_EXPIRED", "The export download has expired.")
            if record.status != DataExportStatus.COMPLETED:
                raise ApiError(409, "EXPORT_NOT_READY", "The export is not ready for download.")
            if record.file_ciphertext is None or record.file_name is None:
                raise ApiError(
                    409,
                    "EXPORT_ARTIFACT_UNAVAILABLE",
                    "The export file is unavailable.",
                )
            try:
                content = self._cipher.decrypt(record.file_ciphertext).encode("utf-8")
            except PiiCipherError as exc:
                raise ApiError(
                    409,
                    "EXPORT_ARTIFACT_UNAVAILABLE",
                    "The export file is unavailable.",
                ) from exc
            digest = hashlib.sha256(content).hexdigest()
            if record.file_sha256 != digest:
                raise ApiError(
                    409,
                    "EXPORT_ARTIFACT_UNAVAILABLE",
                    "The export file failed its integrity check.",
                )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="data_export.downloaded",
                resource_type="data_export",
                resource_id=record.id,
                trace_id=trace_id,
                event_data={
                    "export_type": record.export_type.value,
                    "include_sensitive": record.include_sensitive,
                    "row_count": record.row_count,
                    "file_sha256": digest,
                },
            )
            return ExportDownload(
                content=content,
                file_name=record.file_name,
                content_type=record.content_type or "text/csv; charset=utf-8",
            )

    async def _record(
        self,
        session: AsyncSession,
        *,
        scope: ExportScope,
        export_id: uuid.UUID,
    ) -> DataExportRequest:
        record = await session.scalar(
            select(DataExportRequest).where(
                DataExportRequest.id == export_id,
                *self._access_filters(scope),
            )
        )
        if record is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "Export request not found.")
        return record

    @staticmethod
    async def _expire_due(session: AsyncSession, *, filters: tuple[object, ...]) -> None:
        records = (
            await session.scalars(
                select(DataExportRequest).where(
                    *filters,
                    DataExportRequest.status == DataExportStatus.COMPLETED,
                    DataExportRequest.expires_at <= datetime.now(UTC),
                )
            )
        ).all()
        for record in records:
            ExportStore._expire_record(record)

    @staticmethod
    def _expire_record(record: DataExportRequest) -> None:
        if (
            record.status == DataExportStatus.COMPLETED
            and record.expires_at is not None
            and record.expires_at <= datetime.now(UTC)
        ):
            record.status = DataExportStatus.EXPIRED
            record.file_ciphertext = None
            record.failure_code = None

    @staticmethod
    def _access_filters(scope: ExportScope) -> tuple[object, ...]:
        filters: list[object] = [
            DataExportRequest.tenant_id == scope.tenant_id,
            DataExportRequest.company_id == scope.company_id,
        ]
        if scope.role not in {"company_admin", "platform_admin"}:
            filters.append(DataExportRequest.requested_by == scope.actor_user_id)
        if scope.is_card_owner:
            filters.extend(
                (
                    DataExportRequest.scope_kind == "card_owner",
                    DataExportRequest.owner_user_id == scope.actor_user_id,
                )
            )
        return tuple(filters)

    @staticmethod
    async def _set_scope(session: AsyncSession, scope: ExportScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    @staticmethod
    def _view(record: DataExportRequest) -> ExportRequestView:
        return ExportRequestView(
            id=record.id,
            export_type=record.export_type.value,
            status=record.status.value,
            include_sensitive=record.include_sensitive,
            row_count=record.row_count,
            file_name=record.file_name,
            content_type=record.content_type,
            failure_code=record.failure_code,
            created_at=record.created_at,
            completed_at=record.completed_at,
            expires_at=record.expires_at,
        )


__all__ = ["ExportDownload", "ExportScope", "ExportStore", "ExportType"]
