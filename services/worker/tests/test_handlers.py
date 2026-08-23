from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from cf_worker.domain import (
    ClaimedEvent,
    ExportIntent,
    HandlerResult,
    OutboxRecord,
    PermanentEventError,
    VisitDailyDigestSnapshot,
    VisitNotificationSnapshot,
    WeComVisitCard,
)
from cf_worker.handlers import EventHandlerRegistry


class StubRepository:
    privacy_owner = uuid.uuid4()
    summary_owner = uuid.uuid4()

    def __init__(self) -> None:
        self.wecom_messages: list[dict[str, Any]] = []

    def admin_base_url(self) -> str:
        return "https://example.test/c/admin"

    async def tenant_slug(self, _event: OutboxRecord) -> str:
        return "tuotu"

    async def privacy_recipient(self, _event: OutboxRecord) -> uuid.UUID:
        return self.privacy_owner

    async def summary_recipient(self, _event: OutboxRecord) -> uuid.UUID:
        return self.summary_owner

    async def send_wecom_lead_notification(
        self,
        _event: OutboxRecord,
        *,
        lead_id: uuid.UUID,
        owner_user_id: uuid.UUID,
    ) -> bool:
        assert lead_id
        assert owner_user_id
        return True

    async def visit_notification_snapshot(
        self,
        event: OutboxRecord,
        *,
        visit_id: uuid.UUID,
        report: bool,
    ) -> VisitNotificationSnapshot:
        assert event.aggregate_type == "visit"
        assert event.aggregate_id == visit_id
        return VisitNotificationSnapshot(
            visit_id=visit_id,
            recipient_user_ids=(self.summary_owner,),
            in_app_enabled=True,
            wecom_enabled=True,
            card_display_name="拓浙AI生态",
            visitor_label="微信访客（未识别）",
            visitor_channel="wechat",
            started_at=datetime.now(UTC),
            duration_seconds=126.0 if report else 0.0,
            page_count=4 if report else 1,
            question_count=2 if report else 0,
            share_count=1 if report else 0,
            cta_count=0,
            engagement_level="high" if report else "low",
            has_consented_lead=False,
        )

    async def send_wecom_visit_notification(
        self,
        _event: OutboxRecord,
        *,
        recipient_user_ids: tuple[uuid.UUID, ...],
        card: WeComVisitCard,
        report_url: str,
    ) -> int:
        assert recipient_user_ids == (self.summary_owner,)
        self.wecom_messages.append(
            {
                "card": card,
                "report_url": report_url,
            }
        )
        return 1

    async def visit_daily_digest_snapshot(
        self,
        _event: OutboxRecord,
        *,
        digest_date: date,
    ) -> VisitDailyDigestSnapshot:
        return VisitDailyDigestSnapshot(
            digest_date=digest_date,
            recipient_user_ids=(self.summary_owner,),
            in_app_enabled=True,
            wecom_enabled=True,
            visit_count=12,
            unique_visitor_count=7,
            card_count=3,
            question_count=4,
            share_count=2,
            top_card_display_name="拓浙AI生态",
        )

    async def send_wecom_visit_daily_digest(
        self,
        _event: OutboxRecord,
        *,
        recipient_user_ids: tuple[uuid.UUID, ...],
        card: WeComVisitCard,
        report_url: str,
    ) -> int:
        assert recipient_user_ids == (self.summary_owner,)
        self.wecom_messages.append({"card": card, "report_url": report_url})
        return 1

    async def build_export(
        self,
        _event: OutboxRecord,
        *,
        export_id: uuid.UUID,
        requested_by: uuid.UUID,
    ) -> ExportIntent:
        assert requested_by
        return ExportIntent(
            export_id=export_id,
            file_name="leads.csv",
            content_type="text/csv; charset=utf-8",
            content="\ufeffid\r\nlead-1\r\n",
            row_count=1,
        )


class StubEvaluator:
    async def run(self, **_kwargs: Any) -> dict[str, Any]:
        return {"suite_version": "2", "gate": {"passed": True}, "observations": []}


def event(event_type: str, payload: dict[str, Any], *, headers: dict[str, Any] | None = None):
    return OutboxRecord(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        lock_token=uuid.uuid4(),
        event_type=event_type,
        attempt=1,
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload=payload,
        headers=headers or {},
        deduplication_key=str(uuid.uuid4()),
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_lead_handler_creates_only_static_non_pii_notification() -> None:
    record = event(
        "lead.created.v1",
        {
            "lead_id": str(uuid.uuid4()),
            "card_id": str(uuid.uuid4()),
            "owner_user_id": str(uuid.uuid4()),
        },
    )
    result = await EventHandlerRegistry(StubRepository(), StubEvaluator()).handle(record)
    assert result.handler_name == "lead-notification-v1"
    assert len(result.notifications) == 1
    assert "联系方式" in result.notifications[0].body
    assert "@" not in result.notifications[0].body
    assert result.metadata["wecom_notification_delivered"] is True


@pytest.mark.asyncio
async def test_evaluation_handler_returns_versioned_report_and_notification() -> None:
    company_id = uuid.uuid4()
    record = event(
        "knowledge.evaluate.requested.v1",
        {"company_id": str(company_id), "requested_by": str(uuid.uuid4())},
    )
    record = OutboxRecord(
        **{
            **{field: getattr(record, field) for field in record.__dataclass_fields__},
            "company_id": company_id,
        }
    )
    result = await EventHandlerRegistry(StubRepository(), StubEvaluator()).handle(record)
    assert result.report is not None
    assert result.report.schema_version == 1
    assert result.report.status == "passed"
    assert result.result_hash() == result.result_hash()


@pytest.mark.asyncio
async def test_export_handler_returns_artifact_report_and_notification() -> None:
    export_id = uuid.uuid4()
    requested_by = uuid.uuid4()
    record = event(
        "data_export.requested.v1",
        {"export_id": str(export_id), "requested_by": str(requested_by)},
    )
    record = OutboxRecord(
        **{
            **{field: getattr(record, field) for field in record.__dataclass_fields__},
            "aggregate_type": "data_export",
            "aggregate_id": export_id,
        }
    )
    result = await EventHandlerRegistry(StubRepository(), StubEvaluator()).handle(record)
    assert result.export is not None
    assert result.export.content.startswith("\ufeff")
    assert result.report is not None
    assert result.report.result_type == "data_export"
    assert result.report.status == "completed"
    assert result.notifications[0].recipient_user_id == requested_by
    assert len(result.result_hash()) == 64


@pytest.mark.asyncio
async def test_payload_with_pii_marker_or_extra_field_is_rejected() -> None:
    base = {
        "lead_id": str(uuid.uuid4()),
        "card_id": str(uuid.uuid4()),
        "owner_user_id": str(uuid.uuid4()),
    }
    registry = EventHandlerRegistry(StubRepository(), StubEvaluator())
    with pytest.raises(PermanentEventError, match="pii_payload_forbidden"):
        await registry.handle(event("lead.created.v1", base, headers={"contains_pii": True}))
    with pytest.raises(PermanentEventError, match="unexpected_payload_field"):
        await registry.handle(event("lead.created.v1", {**base, "mobile": "13800000000"}))


@pytest.mark.asyncio
async def test_high_intent_visit_report_is_non_pii_and_links_to_the_report() -> None:
    visit_id = uuid.uuid4()
    card_id = uuid.uuid4()
    base = event(
        "visit.report.ready.v1",
        {"visit_id": str(visit_id), "card_id": str(card_id)},
    )
    record = OutboxRecord(
        **{
            **{field: getattr(base, field) for field in base.__dataclass_fields__},
            "aggregate_type": "visit",
            "aggregate_id": visit_id,
        }
    )
    repository = StubRepository()
    result = await EventHandlerRegistry(repository, StubEvaluator()).handle(record)
    assert result.handler_name == "visit-report-notification-v1"
    assert len(result.notifications) == 1
    assert "2 分 6 秒" in result.notifications[0].body
    assert "微信号" not in result.notifications[0].body
    assert repository.wecom_messages
    message = repository.wecom_messages[0]
    card = message["card"]
    assert card.title == "新访问报告已生成"
    assert card.subtitle == "拓浙AI生态"
    assert str(visit_id)[:8] in dict(card.details)["编号"]
    assert card.action_text == "查看完整访问报告"
    assert card.emphasis_title == "较高"
    assert card.cover_url == (
        "https://example.test/c/admin/assets/wecom/visitor-insight-cover.png"
    )
    assert dict(card.details) == {
        "停留": "2 分 6 秒",
        "页面": "4 个",
        "AI提问": "2 次",
        "分享": "1 次",
        "来源": "微信",
        "编号": str(visit_id)[:8],
    }
    report_url = urlsplit(message["report_url"])
    assert report_url.path == "/c/admin/wecom/entry"
    assert parse_qs(report_url.query)["return_to"] == [f"/c/admin/visits?visitId={visit_id}"]


@pytest.mark.asyncio
async def test_ordinary_visit_events_are_deferred_to_daily_digest() -> None:
    visit_id = uuid.uuid4()
    card_id = uuid.uuid4()
    base = event(
        "visit.started.v1",
        {"visit_id": str(visit_id), "card_id": str(card_id)},
    )
    record = OutboxRecord(
        **{
            **{field: getattr(base, field) for field in base.__dataclass_fields__},
            "aggregate_type": "visit",
            "aggregate_id": visit_id,
        }
    )

    repository = StubRepository()
    result = await EventHandlerRegistry(repository, StubEvaluator()).handle(record)
    assert result.handler_name == "visit-ordinary-digest-deferred-v1"
    assert result.notifications == ()
    assert result.metadata["deferred_to_digest"] is True
    assert repository.wecom_messages == []


@pytest.mark.asyncio
async def test_daily_digest_notification_is_non_pii_and_links_to_digest_view() -> None:
    company_id = uuid.uuid4()
    base = event(
        "visit.daily_digest.ready.v1",
        {"company_id": str(company_id), "digest_date": "2026-08-22"},
    )
    record = OutboxRecord(
        **{
            **{field: getattr(base, field) for field in base.__dataclass_fields__},
            "aggregate_type": "company",
            "aggregate_id": company_id,
        }
    )

    repository = StubRepository()
    result = await EventHandlerRegistry(repository, StubEvaluator()).handle(record)
    assert result.handler_name == "visit-daily-digest-notification-v1"
    assert len(result.notifications) == 1
    assert "12 次普通访问" in result.notifications[0].body
    assert repository.wecom_messages
    report_url = urlsplit(repository.wecom_messages[0]["report_url"])
    assert report_url.path == "/c/admin/wecom/entry"
    assert parse_qs(report_url.query)["return_to"] == [
        "/c/admin/visits?date=2026-08-22&view=digest"
    ]


@pytest.mark.asyncio
async def test_unknown_event_is_rejected_without_payload_interpretation() -> None:
    with pytest.raises(PermanentEventError, match="unsupported_event_type"):
        await EventHandlerRegistry(StubRepository(), StubEvaluator()).handle(
            event("unknown.v1", {"secret": "do-not-log"})
        )


def test_handler_result_hash_is_stable() -> None:
    result = HandlerResult(handler_name="test", metadata={"b": 2, "a": 1})
    assert len(result.result_hash()) == 64


def test_claimed_event_contains_no_payload() -> None:
    claim = ClaimedEvent(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        lock_token=uuid.uuid4(),
        event_type="lead.created.v1",
        attempt=1,
    )
    assert not hasattr(claim, "payload")
