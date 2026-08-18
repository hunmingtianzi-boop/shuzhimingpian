from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.api.workflow_schemas import (
    VisitAction,
    VisitEventRequest,
    VisitPageDuration,
    VisitQuestion,
)
from app.db.models import Visit, VisitEvent
from app.services.workflow_store import (
    _behavior_analysis,
    _page_timeline,
    _visit_presentation,
    _visit_started_deduplication_key,
)


def _visit(*, started_at: datetime, ended_at: datetime | None = None, context=None) -> Visit:
    return Visit(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        card_id=uuid.uuid4(),
        visitor_id=uuid.uuid4(),
        source="card_web",
        started_at=started_at,
        ended_at=ended_at,
        context=context or {},
    )


def test_visit_without_events_is_unknown_instead_of_active() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)

    result = _visit_presentation(
        _visit(started_at=now - timedelta(hours=1)),
        last_event_at=None,
        event_count=0,
        now=now,
    )

    assert result.activity_status == "unknown"
    assert result.duration_seconds is None


def test_stale_visit_uses_last_event_as_estimated_end() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
    started_at = now - timedelta(minutes=12)
    last_event_at = started_at + timedelta(minutes=3, seconds=20)

    result = _visit_presentation(
        _visit(
            started_at=started_at,
            context={"visitor_channel": "wechat"},
        ),
        last_event_at=last_event_at,
        event_count=2,
        now=now,
    )

    assert result.activity_status == "estimated"
    assert result.duration_seconds == 200
    assert result.duration_estimated is True
    assert result.visitor_identity_label == "微信访客（未识别）"


def test_recent_wecom_visit_remains_active() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)

    result = _visit_presentation(
        _visit(
            started_at=now - timedelta(minutes=2),
            context={"visitor_channel": "wecom"},
        ),
        last_event_at=now - timedelta(seconds=15),
        event_count=3,
        now=now,
    )

    assert result.activity_status == "active"
    assert result.visitor_channel == "wecom"
    assert result.visitor_identity_label == "企业微信访客（未识别）"


def test_recent_background_transition_is_not_shown_as_active() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
    started_at = now - timedelta(minutes=2)

    result = _visit_presentation(
        _visit(started_at=started_at, context={"activity_state": "background"}),
        last_event_at=now - timedelta(seconds=2),
        event_count=2,
        now=now,
    )

    assert result.activity_status == "estimated"
    assert result.duration_seconds == 118
    assert result.duration_estimated is True


def test_missing_leave_falls_back_after_heartbeat_grace_period() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
    started_at = now - timedelta(minutes=2)

    result = _visit_presentation(
        _visit(started_at=started_at),
        last_event_at=now - timedelta(seconds=46),
        event_count=2,
        now=now,
    )

    assert result.activity_status == "estimated"
    assert result.duration_estimated is True


def test_explicit_leave_is_not_estimated() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
    started_at = now - timedelta(minutes=4)
    ended_at = started_at + timedelta(seconds=90)

    result = _visit_presentation(
        _visit(started_at=started_at, ended_at=ended_at),
        last_event_at=ended_at,
        event_count=2,
        now=now,
    )

    assert result.activity_status == "ended"
    assert result.duration_seconds == 90
    assert result.duration_estimated is False


def test_each_browser_entry_can_notify_for_an_existing_visit() -> None:
    visit_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    request = VisitEventRequest(
        event_id=uuid.uuid4(),
        event_type="page_view",
        metadata={"visit_entry_id": str(entry_id)},
    )

    assert _visit_started_deduplication_key(
        visit_id=visit_id,
        request=request,
        first_page_view=False,
    ) == f"visit-started:{visit_id}:{entry_id}"


def test_navigation_without_a_new_browser_entry_does_not_repeat_notification() -> None:
    request = VisitEventRequest(
        event_id=uuid.uuid4(),
        event_type="page_view",
        metadata={"page_key": "product:a"},
    )

    assert (
        _visit_started_deduplication_key(
            visit_id=uuid.uuid4(),
            request=request,
            first_page_view=False,
        )
        is None
    )


def test_page_timeline_preserves_each_navigation_segment() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
    visit = _visit(started_at=now)
    events = [
        VisitEvent(
            id=uuid.uuid4(),
            tenant_id=visit.tenant_id,
            company_id=visit.company_id,
            visit_id=visit.id,
            event_type="page_view",
            object_type="card",
            object_id="company:overview",
            occurred_at=now,
            metadata_json={"page_key": "company:overview", "page_title": "企业首页"},
        ),
        VisitEvent(
            id=uuid.uuid4(),
            tenant_id=visit.tenant_id,
            company_id=visit.company_id,
            visit_id=visit.id,
            event_type="heartbeat",
            object_type="card",
            object_id="company:overview",
            occurred_at=now + timedelta(seconds=15),
            metadata_json={"page_key": "company:overview", "duration_ms": 15_000},
        ),
        VisitEvent(
            id=uuid.uuid4(),
            tenant_id=visit.tenant_id,
            company_id=visit.company_id,
            visit_id=visit.id,
            event_type="page_view",
            object_type="product",
            object_id="product-a",
            occurred_at=now + timedelta(seconds=16),
            metadata_json={"page_key": "product:a", "page_title": "产品 A"},
        ),
        VisitEvent(
            id=uuid.uuid4(),
            tenant_id=visit.tenant_id,
            company_id=visit.company_id,
            visit_id=visit.id,
            event_type="leave",
            object_type="product",
            object_id="product-a",
            occurred_at=now + timedelta(seconds=46),
            metadata_json={"page_key": "product:a", "duration_ms": 30_000},
        ),
    ]
    presentation = _visit_presentation(
        visit, last_event_at=events[-1].occurred_at, event_count=len(events), now=now
    )

    timeline = _page_timeline(events, presentation=presentation)

    assert [(item.page_title, item.duration_seconds) for item in timeline] == [
        ("企业首页", 15.0),
        ("产品 A", 30.0),
    ]
    assert timeline[0].exit_reason == "navigation"
    assert timeline[1].exit_reason == "leave"


def test_page_timeline_marks_hidden_wecom_webview_as_background() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
    visit = _visit(started_at=now, context={"activity_state": "background"})
    events = [
        VisitEvent(
            id=uuid.uuid4(),
            tenant_id=visit.tenant_id,
            company_id=visit.company_id,
            visit_id=visit.id,
            event_type="page_view",
            object_type="card",
            occurred_at=now,
            metadata_json={"page_key": "company:overview", "page_title": "企业首页"},
        ),
        VisitEvent(
            id=uuid.uuid4(),
            tenant_id=visit.tenant_id,
            company_id=visit.company_id,
            visit_id=visit.id,
            event_type="heartbeat",
            object_type="card",
            occurred_at=now + timedelta(seconds=12),
            metadata_json={
                "page_key": "company:overview",
                "page_title": "企业首页",
                "duration_ms": 12_000,
                "lifecycle_state": "background",
            },
        ),
    ]
    presentation = _visit_presentation(
        visit,
        last_event_at=events[-1].occurred_at,
        event_count=len(events),
        now=now + timedelta(seconds=13),
    )

    timeline = _page_timeline(events, presentation=presentation)

    assert len(timeline) == 1
    assert timeline[0].duration_seconds == 12.0
    assert timeline[0].exit_reason == "background"


def test_behavior_analysis_explains_score_with_observed_and_inferred_evidence() -> None:
    now = datetime(2026, 8, 8, 0, 0, tzinfo=UTC)
    analysis = _behavior_analysis(
        page_durations=[
            VisitPageDuration(
                page_key="product:a",
                page_title="产品 A",
                object_type="product",
                object_id="a",
                duration_seconds=120,
                view_count=2,
                last_viewed_at=now,
            ),
            VisitPageDuration(
                page_key="company:overview",
                page_title="企业首页",
                object_type="card",
                object_id="overview",
                duration_seconds=60,
                view_count=1,
                last_viewed_at=now,
            ),
        ],
        actions=[
            VisitAction(
                event_id=uuid.uuid4(),
                action_type="cta_click",
                action_label="打开联系表单",
                object_type="contact",
                object_id="lead_form",
                occurred_at=now,
            )
        ],
        questions=[
            VisitQuestion(
                message_id=uuid.uuid4(),
                conversation_id=uuid.uuid4(),
                question="怎么合作？",
                asked_at=now,
                answer_status="completed",
                answer="可以留下联系方式。",
                answered_at=now,
                response_seconds=1,
            )
        ],
    )

    assert analysis.engagement_score >= 60
    assert analysis.engagement_level == "medium"
    assert analysis.intent_level == "high"
    assert analysis.tracked_duration_seconds == 180
    assert any(signal.basis == "observed" for signal in analysis.signals)
    assert any(signal.basis == "inferred" for signal in analysis.signals)
