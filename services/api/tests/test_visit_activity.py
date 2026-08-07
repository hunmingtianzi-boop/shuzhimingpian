from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.db.models import Visit
from app.services.workflow_store import _visit_presentation


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
