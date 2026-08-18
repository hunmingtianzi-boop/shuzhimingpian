from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

from cf_worker.domain import (
    EvaluationRunner,
    ExportIntent,
    HandlerResult,
    NotificationIntent,
    OutboxRecord,
    OutboxRepository,
    PermanentEventError,
    ReportIntent,
)

_UUID_KEYS_BY_EVENT: dict[str, frozenset[str]] = {
    "data_export.requested.v1": frozenset({"export_id", "requested_by"}),
    "knowledge.evaluate.requested.v1": frozenset({"company_id", "requested_by"}),
    "lead.created.v1": frozenset({"lead_id", "card_id", "owner_user_id"}),
    "privacy_request.created.v1": frozenset({"privacy_request_id"}),
    "enterprise.created.v1": frozenset({"tenant_id", "company_id", "admin_user_id"}),
    "visit_summary.ready.v1": frozenset({"summary_id", "conversation_id", "owner_user_id"}),
    "visit_summary.generated.v1": frozenset({"summary_id", "conversation_id", "owner_user_id"}),
    "visit.started.v1": frozenset({"visit_id", "card_id"}),
    "visit.report.ready.v1": frozenset({"visit_id", "card_id"}),
}
_OPTIONAL_KEYS_BY_EVENT: dict[str, frozenset[str]] = {
    "privacy_request.created.v1": frozenset({"request_type"}),
    "visit_summary.ready.v1": frozenset({"owner_user_id"}),
    "visit_summary.generated.v1": frozenset({"owner_user_id"}),
}
_PRIVACY_REQUEST_TYPES = frozenset({"access", "correction", "deletion", "withdraw_consent"})


class EventHandlerRegistry:
    def __init__(self, repository: OutboxRepository, evaluator: EvaluationRunner) -> None:
        self._repository = repository
        self._evaluator = evaluator

    async def handle(self, event: OutboxRecord) -> HandlerResult:
        payload = _validated_payload(event)
        if event.event_type == "knowledge.evaluate.requested.v1":
            return await self._evaluate(event, payload)
        if event.event_type == "data_export.requested.v1":
            return await self._data_export(event, payload)
        if event.event_type == "lead.created.v1":
            return await self._lead(event, payload)
        if event.event_type == "privacy_request.created.v1":
            return await self._privacy_request(event, payload)
        if event.event_type == "enterprise.created.v1":
            return self._enterprise(event, payload)
        if event.event_type in {"visit_summary.ready.v1", "visit_summary.generated.v1"}:
            return await self._visit_summary(event, payload)
        if event.event_type in {"visit.started.v1", "visit.report.ready.v1"}:
            return await self._visit_notification(event, payload)
        raise PermanentEventError("unsupported_event_type")

    async def _data_export(
        self,
        event: OutboxRecord,
        payload: Mapping[str, Any],
    ) -> HandlerResult:
        export_id = _uuid_value(payload, "export_id")
        requested_by = _uuid_value(payload, "requested_by")
        if event.aggregate_type != "data_export" or event.aggregate_id != export_id:
            raise PermanentEventError("payload_aggregate_mismatch")
        export: ExportIntent = await self._repository.build_export(
            event,
            export_id=export_id,
            requested_by=requested_by,
        )
        return HandlerResult(
            handler_name="data-export-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=requested_by,
                    notification_type="data_export_ready",
                    title="数据导出已完成",
                    body="导出文件已生成，请在 24 小时内下载。",
                    resource_type="data_export",
                    resource_id=export_id,
                ),
            ),
            export=export,
            report=ReportIntent(
                result_type="data_export",
                schema_version=1,
                status="completed",
                report={
                    "export_id": str(export_id),
                    "row_count": export.row_count,
                    "file_sha256": export.content_sha256(),
                },
            ),
        )

    async def _evaluate(
        self,
        event: OutboxRecord,
        payload: Mapping[str, Any],
    ) -> HandlerResult:
        requested_by = _uuid_value(payload, "requested_by")
        _require_scope_uuid(payload, "company_id", event.company_id)
        tenant_slug = await self._repository.tenant_slug(event)
        report = await self._evaluator.run(
            tenant_id=event.tenant_id,
            company_id=event.company_id,
            tenant_slug=tenant_slug,
        )
        gate = report.get("gate")
        passed = bool(gate.get("passed")) if isinstance(gate, dict) else False
        return HandlerResult(
            handler_name="knowledge-evaluation-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=requested_by,
                    notification_type="knowledge_evaluation_ready",
                    title="知识评测已完成",
                    body=(
                        "知识问答评测已通过发布门槛。"
                        if passed
                        else "知识问答评测未通过发布门槛，请查看评测结果并修正。"
                    ),
                    resource_type="evaluation_job",
                    resource_id=event.id,
                ),
            ),
            report=ReportIntent(
                result_type="rag_evaluation",
                schema_version=1,
                status="passed" if passed else "failed_gate",
                report=report,
            ),
            metadata={"gate_passed": passed},
        )

    async def _lead(self, event: OutboxRecord, payload: Mapping[str, Any]) -> HandlerResult:
        lead_id = _uuid_value(payload, "lead_id")
        owner_user_id = _uuid_value(payload, "owner_user_id")
        _uuid_value(payload, "card_id")
        wecom_delivered = await self._repository.send_wecom_lead_notification(
            event,
            lead_id=lead_id,
            owner_user_id=owner_user_id,
        )
        return HandlerResult(
            handler_name="lead-notification-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=owner_user_id,
                    notification_type="lead_created",
                    title="收到新线索",
                    body="访客已主动留下联系方式和需求，请及时跟进。",
                    resource_type="lead",
                    resource_id=lead_id,
                ),
            ),
            metadata={
                "event_id": str(event.id),
                "wecom_notification_delivered": wecom_delivered,
            },
        )

    async def _privacy_request(
        self,
        event: OutboxRecord,
        payload: Mapping[str, Any],
    ) -> HandlerResult:
        request_id = _uuid_value(payload, "privacy_request_id")
        request_type = payload.get("request_type")
        if request_type is not None and request_type not in _PRIVACY_REQUEST_TYPES:
            raise PermanentEventError("invalid_privacy_request_type")
        recipient = await self._repository.privacy_recipient(event)
        if recipient is None:
            raise PermanentEventError("privacy_recipient_not_found")
        return HandlerResult(
            handler_name="privacy-notification-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=recipient,
                    notification_type="privacy_request_created",
                    title="收到隐私权利请求",
                    body="访客提交了数据权利请求，请按合规流程及时处理。",
                    resource_type="privacy_request",
                    resource_id=request_id,
                ),
            ),
        )

    @staticmethod
    def _enterprise(event: OutboxRecord, payload: Mapping[str, Any]) -> HandlerResult:
        _require_scope_uuid(payload, "tenant_id", event.tenant_id)
        _require_scope_uuid(payload, "company_id", event.company_id)
        admin_user_id = _uuid_value(payload, "admin_user_id")
        return HandlerResult(
            handler_name="enterprise-onboarding-notification-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=admin_user_id,
                    notification_type="enterprise_onboarding_ready",
                    title="企业空间已开通",
                    body="企业空间和初始名片已创建，请完善企业资料并发布首批知识。",
                    resource_type="company",
                    resource_id=event.company_id,
                ),
            ),
        )

    async def _visit_summary(
        self,
        event: OutboxRecord,
        payload: Mapping[str, Any],
    ) -> HandlerResult:
        summary_id = _uuid_value(payload, "summary_id")
        _uuid_value(payload, "conversation_id")
        raw_owner = payload.get("owner_user_id")
        recipient = (
            _as_uuid(raw_owner) if raw_owner else await self._repository.summary_recipient(event)
        )
        if recipient is None:
            raise PermanentEventError("summary_recipient_not_found")
        return HandlerResult(
            handler_name="visit-summary-notification-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=recipient,
                    notification_type="visit_summary_ready",
                    title="新拜访纪要已生成",
                    body="AI 已生成结构化纪要，请及时查看并人工确认。",
                    resource_type="visit_summary",
                    resource_id=summary_id,
                ),
            ),
        )

    async def _visit_notification(
        self,
        event: OutboxRecord,
        payload: Mapping[str, Any],
    ) -> HandlerResult:
        visit_id = _uuid_value(payload, "visit_id")
        _uuid_value(payload, "card_id")
        if event.aggregate_type != "visit" or event.aggregate_id != visit_id:
            raise PermanentEventError("payload_aggregate_mismatch")
        report = event.event_type == "visit.report.ready.v1"
        snapshot = await self._repository.visit_notification_snapshot(
            event,
            visit_id=visit_id,
            report=report,
        )
        if snapshot is None:
            raise PermanentEventError("visit_not_found")

        channel_label = {
            "web": "网页",
            "wechat": "微信",
            "wecom": "企业微信",
        }.get(snapshot.visitor_channel, "网页")
        if report:
            level_label = {"low": "较低", "medium": "中等", "high": "较高"}.get(
                snapshot.engagement_level,
                "较低",
            )
            title = "新访问报告已生成"
            body = (
                f"访客在“{snapshot.card_display_name}”停留 "
                f"{_duration_label(snapshot.duration_seconds)}，"
                f"浏览 {snapshot.page_count} 个页面，向 AI 提问 {snapshot.question_count} 次，"
                f"分享 {snapshot.share_count} 次，综合意向{level_label}。"
            )
            notification_type = "visit_report_ready"
        else:
            title = "有人正在查看名片"
            body = (
                f"{snapshot.visitor_label}正在查看“{snapshot.card_display_name}”，"
                f"来源：{channel_label}。"
            )
            notification_type = "visit_started"

        notifications = (
            tuple(
                NotificationIntent(
                    recipient_user_id=recipient,
                    notification_type=notification_type,
                    title=title,
                    body=body,
                    resource_type="visit",
                    resource_id=visit_id,
                )
                for recipient in snapshot.recipient_user_ids
            )
            if snapshot.in_app_enabled
            else ()
        )
        admin_base_url = self._repository.admin_base_url()
        report_entry_url = _wecom_visit_report_entry_url(admin_base_url, visit_id)
        # The visit identifier keeps different anonymous visits distinguishable
        # without exposing personal data in the application message.
        wecom_description = f"{body}\n访问编号：{str(visit_id)[:8]}"
        wecom_delivered = (
            await self._repository.send_wecom_visit_notification(
                event,
                recipient_user_ids=snapshot.recipient_user_ids,
                title=title,
                description=wecom_description,
                report_url=report_entry_url,
            )
            if snapshot.wecom_enabled and report_entry_url is not None
            else 0
        )
        return HandlerResult(
            handler_name=(
                "visit-report-notification-v1" if report else "visit-started-notification-v1"
            ),
            notifications=notifications,
            metadata={
                "recipient_count": len(snapshot.recipient_user_ids),
                "wecom_delivered": wecom_delivered,
                "suppressed": not snapshot.in_app_enabled and not snapshot.wecom_enabled,
            },
        )


def _validated_payload(event: OutboxRecord) -> dict[str, Any]:
    if event.headers.get("contains_pii") is True:
        raise PermanentEventError("pii_payload_forbidden")
    required = _UUID_KEYS_BY_EVENT.get(event.event_type)
    if required is None:
        raise PermanentEventError("unsupported_event_type")
    optional = _OPTIONAL_KEYS_BY_EVENT.get(event.event_type, frozenset())
    allowed = required | optional
    if set(event.payload) - allowed:
        raise PermanentEventError("unexpected_payload_field")
    missing = required - optional - set(event.payload)
    if missing:
        raise PermanentEventError("missing_payload_field")
    for key in required & set(event.payload):
        _uuid_value(event.payload, key)
    return dict(event.payload)


def _duration_label(seconds: float) -> str:
    rounded = max(0, round(seconds))
    if rounded < 60:
        return f"{rounded} 秒"
    minutes, remaining = divmod(rounded, 60)
    return f"{minutes} 分 {remaining} 秒" if remaining else f"{minutes} 分"


def _wecom_visit_report_entry_url(
    admin_base_url: str | None,
    visit_id: uuid.UUID,
) -> str | None:
    """Route a WeCom card through the app entry so OAuth returns to the report."""

    if not admin_base_url:
        return None
    parsed = urlsplit(admin_base_url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return None
    base_path = parsed.path.rstrip("/")
    report_path = f"{base_path}/visits?visitId={visit_id}"
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"{base_path}/wecom/entry",
            urlencode({"return_to": report_path}),
            "",
        )
    )


def _uuid_value(payload: Mapping[str, Any], key: str) -> uuid.UUID:
    if key not in payload:
        raise PermanentEventError("missing_payload_field")
    value = _as_uuid(payload[key])
    if value is None:
        raise PermanentEventError("invalid_uuid_payload")
    return value


def _as_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, bool):
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _require_scope_uuid(payload: Mapping[str, Any], key: str, expected: uuid.UUID) -> None:
    if _uuid_value(payload, key) != expected:
        raise PermanentEventError("payload_scope_mismatch")


__all__ = ["EventHandlerRegistry"]
