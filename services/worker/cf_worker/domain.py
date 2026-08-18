from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ClaimedEvent:
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    lock_token: uuid.UUID
    event_type: str
    attempt: int


@dataclass(frozen=True, slots=True)
class ClaimedContentImport:
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    lock_token: uuid.UUID
    requested_by: uuid.UUID
    attempt: int
    max_attempts: int


@dataclass(frozen=True, slots=True)
class OutboxRecord(ClaimedEvent):
    aggregate_type: str
    aggregate_id: uuid.UUID
    payload: dict[str, Any]
    headers: dict[str, Any]
    deduplication_key: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationIntent:
    recipient_user_id: uuid.UUID
    notification_type: str
    title: str
    body: str
    resource_type: str | None = None
    resource_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class VisitNotificationSnapshot:
    visit_id: uuid.UUID
    recipient_user_ids: tuple[uuid.UUID, ...]
    in_app_enabled: bool
    wecom_enabled: bool
    card_display_name: str
    visitor_label: str
    visitor_channel: str
    started_at: datetime
    duration_seconds: float
    page_count: int
    question_count: int
    share_count: int
    cta_count: int
    engagement_level: str


@dataclass(frozen=True, slots=True)
class ReportIntent:
    result_type: str
    schema_version: int
    status: str
    report: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExportIntent:
    export_id: uuid.UUID
    file_name: str
    content_type: str
    content: str = field(repr=False)
    row_count: int

    def content_sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class HandlerResult:
    handler_name: str
    notifications: tuple[NotificationIntent, ...] = ()
    report: ReportIntent | None = None
    export: ExportIntent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def result_hash(self) -> str:
        payload = {
            "handler_name": self.handler_name,
            "notifications": [
                {
                    "recipient_user_id": str(item.recipient_user_id),
                    "notification_type": item.notification_type,
                    "title": item.title,
                    "body": item.body,
                    "resource_type": item.resource_type,
                    "resource_id": str(item.resource_id) if item.resource_id else None,
                }
                for item in self.notifications
            ],
            "report": (
                {
                    "result_type": self.report.result_type,
                    "schema_version": self.report.schema_version,
                    "status": self.report.status,
                    "report": self.report.report,
                }
                if self.report
                else None
            ),
            "export": (
                {
                    "export_id": str(self.export.export_id),
                    "file_name": self.export.file_name,
                    "content_type": self.export.content_type,
                    "content_sha256": self.export.content_sha256(),
                    "row_count": self.export.row_count,
                }
                if self.export
                else None
            ),
            "metadata": self.metadata,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class PermanentEventError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EvaluationRunner(Protocol):
    async def run(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        tenant_slug: str,
    ) -> dict[str, Any]: ...


class OutboxRepository(Protocol):
    async def claim(self) -> tuple[ClaimedEvent, ...]: ...

    async def load_leased(self, claim: ClaimedEvent) -> OutboxRecord | None: ...

    async def renew_lease(self, event: OutboxRecord) -> bool: ...

    async def tenant_slug(self, event: OutboxRecord) -> str: ...

    async def privacy_recipient(self, event: OutboxRecord) -> uuid.UUID | None: ...

    async def summary_recipient(self, event: OutboxRecord) -> uuid.UUID | None: ...

    def admin_base_url(self) -> str | None: ...

    async def send_wecom_lead_notification(
        self,
        event: OutboxRecord,
        *,
        lead_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ) -> bool: ...

    async def visit_notification_snapshot(
        self,
        event: OutboxRecord,
        *,
        visit_id: uuid.UUID,
        report: bool,
    ) -> VisitNotificationSnapshot | None: ...

    async def send_wecom_visit_notification(
        self,
        event: OutboxRecord,
        *,
        recipient_user_ids: tuple[uuid.UUID, ...],
        content: str,
    ) -> int: ...

    async def build_export(
        self,
        event: OutboxRecord,
        *,
        export_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> ExportIntent: ...

    async def complete(self, event: OutboxRecord, result: HandlerResult) -> str: ...

    async def fail(self, event: OutboxRecord, *, error_code: str, permanent: bool) -> str: ...


__all__ = [
    "ClaimedContentImport",
    "ClaimedEvent",
    "EvaluationRunner",
    "ExportIntent",
    "HandlerResult",
    "NotificationIntent",
    "OutboxRecord",
    "OutboxRepository",
    "PermanentEventError",
    "ReportIntent",
    "VisitNotificationSnapshot",
]
