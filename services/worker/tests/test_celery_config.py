from __future__ import annotations

from cf_worker.celery_app import celery_app, settings


def test_celery_uses_redis_late_ack_and_visibility_larger_than_database_lease() -> None:
    assert celery_app.conf.broker_url.startswith("redis://")
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert (
        celery_app.conf.broker_transport_options["visibility_timeout"]
        > settings.outbox_lease_seconds
    )
    poll_schedule = celery_app.conf.beat_schedule["poll-postgresql-outbox"]
    assert poll_schedule["schedule"] == settings.outbox_poll_seconds
    assert poll_schedule["options"] == {
        "queue": "outbox.poll",
        "expires": settings.outbox_poll_seconds * 2,
    }
    retention_schedule = celery_app.conf.beat_schedule["purge-expired-visitor-profiles"]
    assert retention_schedule["task"] == "cf_worker.purge_expired_visitor_profiles"
    assert retention_schedule["schedule"] == settings.profile_retention_purge_seconds
    assert retention_schedule["options"] == {
        "queue": "outbox.poll",
        "expires": settings.profile_retention_purge_seconds,
    }
    visit_reports = celery_app.conf.beat_schedule["enqueue-inactive-visit-reports"]
    assert visit_reports["task"] == "cf_worker.enqueue_inactive_visit_reports"
    assert visit_reports["schedule"] == settings.visit_report_poll_seconds
    assert visit_reports["options"] == {
        "queue": "outbox.poll",
        "expires": settings.visit_report_poll_seconds * 2,
    }
    onboarding_retention = celery_app.conf.beat_schedule[
        "purge-expired-platform-onboarding-sessions"
    ]
    assert onboarding_retention["task"] == "cf_worker.purge_expired_platform_onboarding_sessions"
    assert onboarding_retention["schedule"] == settings.platform_onboarding_retention_purge_seconds
    assert onboarding_retention["options"] == {
        "queue": "outbox.poll",
        "expires": settings.platform_onboarding_retention_purge_seconds,
    }
    scheduled_publish = celery_app.conf.beat_schedule["poll-scheduled-publishes"]
    assert scheduled_publish["task"] == "cf_worker.poll_scheduled_publishes"
    assert scheduled_publish["schedule"] == settings.scheduled_publish_poll_seconds
    assert scheduled_publish["options"] == {
        "queue": "outbox.poll",
        "expires": settings.scheduled_publish_poll_seconds * 2,
    }
    imports = celery_app.conf.beat_schedule["poll-knowledge-imports"]
    assert imports["task"] == "cf_worker.poll_knowledge_imports"
    assert imports["schedule"] == settings.knowledge_import_poll_seconds
    content_imports = celery_app.conf.beat_schedule["poll-content-imports"]
    assert content_imports["task"] == "cf_worker.poll_content_imports"
    assert content_imports["schedule"] == settings.content_import_poll_seconds
    assert content_imports["options"] == {
        "queue": "outbox.poll",
        "expires": settings.content_import_poll_seconds * 2,
    }
