from __future__ import annotations

from celery import Celery

from cf_worker.config import get_worker_settings
from cf_worker.logging import configure_worker_logging

settings = get_worker_settings()
configure_worker_logging(settings.worker_log_level)

celery_app = Celery(
    "cf-ai-card-worker",
    broker=settings.broker_url,
    include=["cf_worker.tasks", "cf_worker.health"],
)
celery_app.conf.update(
    task_default_queue="outbox.poll",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_ignore_result=True,
    task_track_started=False,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    worker_soft_shutdown_timeout=20.0,
    worker_enable_soft_shutdown_on_idle=True,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": settings.outbox_lease_seconds * 2,
        "global_keyprefix": "cf-ai-card-worker_",
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "poll-postgresql-outbox": {
            "task": "cf_worker.poll_outbox",
            "schedule": settings.outbox_poll_seconds,
            "options": {"queue": "outbox.poll", "expires": settings.outbox_poll_seconds * 2},
        },
        "purge-expired-visitor-profiles": {
            "task": "cf_worker.purge_expired_visitor_profiles",
            "schedule": settings.profile_retention_purge_seconds,
            "options": {
                "queue": "outbox.poll",
                "expires": settings.profile_retention_purge_seconds,
            },
        },
        "enqueue-inactive-visit-reports": {
            "task": "cf_worker.enqueue_inactive_visit_reports",
            "schedule": settings.visit_report_poll_seconds,
            "options": {
                "queue": "outbox.poll",
                "expires": settings.visit_report_poll_seconds * 2,
            },
        },
        "purge-expired-platform-onboarding-sessions": {
            "task": "cf_worker.purge_expired_platform_onboarding_sessions",
            "schedule": settings.platform_onboarding_retention_purge_seconds,
            "options": {
                "queue": "outbox.poll",
                "expires": settings.platform_onboarding_retention_purge_seconds,
            },
        },
        "poll-scheduled-publishes": {
            "task": "cf_worker.poll_scheduled_publishes",
            "schedule": settings.scheduled_publish_poll_seconds,
            "options": {
                "queue": "outbox.poll",
                "expires": settings.scheduled_publish_poll_seconds * 2,
            },
        },
        "poll-knowledge-imports": {
            "task": "cf_worker.poll_knowledge_imports",
            "schedule": settings.knowledge_import_poll_seconds,
            "options": {
                "queue": "outbox.poll",
                "expires": settings.knowledge_import_poll_seconds * 2,
            },
        },
    },
)


__all__ = ["celery_app"]
