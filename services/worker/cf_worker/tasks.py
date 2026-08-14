from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable

from app.core.redaction import redact_sensitive_text
from celery import shared_task
from celery.utils.log import get_task_logger
from sqlalchemy.exc import SQLAlchemyError

from cf_worker.config import get_worker_settings
from cf_worker.domain import ClaimedEvent
from cf_worker.evaluation import ApiEvaluationRunner
from cf_worker.handlers import EventHandlerRegistry
from cf_worker.knowledge_imports import KnowledgeImportError, KnowledgeImportExecutor
from cf_worker.repository import PostgresOutboxRepository
from cf_worker.scheduled_publish import ScheduledPublishExecutor
from cf_worker.service import WorkerService

logger = get_task_logger(__name__)

_DATABASE_FAILURE_COOLDOWN_SECONDS = 30.0
_database_paused_until = 0.0


def _run_database_poll(task_name: str, run: Callable[[], Awaitable[int]]) -> int:
    """Rate-limit infrastructure failures shared by all periodic DB pollers."""
    global _database_paused_until
    now = time.monotonic()
    if now < _database_paused_until:
        return 0
    try:
        result = asyncio.run(run())
    except SQLAlchemyError as exc:
        _database_paused_until = time.monotonic() + _DATABASE_FAILURE_COOLDOWN_SECONDS
        logger.error(
            "worker database poll paused",
            extra={"task": task_name, "error_type": type(exc).__name__},
        )
        return 0
    _database_paused_until = 0.0
    return result


def _service(
    repository: PostgresOutboxRepository,
) -> WorkerService:
    settings = get_worker_settings()
    return WorkerService(
        repository=repository,
        handlers=EventHandlerRegistry(repository, ApiEvaluationRunner(settings)),
        settings=settings,
    )


@shared_task(
    name="cf_worker.poll_outbox",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def poll_outbox() -> int:
    async def run() -> int:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            service = _service(repository)

            def send(claim: ClaimedEvent) -> None:
                process_outbox_event.apply_async(
                    kwargs={
                        "event_id": str(claim.id),
                        "tenant_id": str(claim.tenant_id),
                        "company_id": str(claim.company_id),
                        "lock_token": str(claim.lock_token),
                        "event_type": claim.event_type,
                        "attempt": claim.attempt,
                    },
                    queue="outbox.process",
                )

            return await service.dispatch_once(send)
        finally:
            await repository.close()

    return _run_database_poll("poll_outbox", run)


@shared_task(
    name="cf_worker.process_outbox_event",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_outbox_event(
    *,
    event_id: str,
    tenant_id: str,
    company_id: str,
    lock_token: str,
    event_type: str,
    attempt: int,
) -> str:
    claim = ClaimedEvent(
        id=uuid.UUID(event_id),
        tenant_id=uuid.UUID(tenant_id),
        company_id=uuid.UUID(company_id),
        lock_token=uuid.UUID(lock_token),
        event_type=event_type[:160],
        attempt=max(int(attempt), 1),
    )

    async def run() -> str:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            return await _service(repository).process(claim)
        finally:
            await repository.close()

    return asyncio.run(run())


@shared_task(
    name="cf_worker.purge_expired_visitor_profiles",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def purge_expired_visitor_profiles() -> int:
    async def run() -> int:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            return await repository.purge_expired_visitor_profiles()
        finally:
            await repository.close()

    deleted = _run_database_poll("purge_expired_visitor_profiles", run)
    logger.info("visitor profile retention purge completed", extra={"deleted": deleted})
    return deleted


@shared_task(
    name="cf_worker.purge_expired_platform_onboarding_sessions",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def purge_expired_platform_onboarding_sessions() -> int:
    async def run() -> int:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            return await repository.purge_expired_platform_onboarding_sessions()
        finally:
            await repository.close()

    processed = _run_database_poll("purge_expired_platform_onboarding_sessions", run)
    logger.info(
        "platform onboarding retention purge completed",
        extra={"processed": processed},
    )
    return processed


@shared_task(
    name="cf_worker.poll_scheduled_publishes",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def poll_scheduled_publishes() -> int:
    async def run() -> int:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            executor = ScheduledPublishExecutor(repository, settings)
            claims = await repository.claim_scheduled_publishes()
            completed = 0
            for claim in claims:
                try:
                    await executor.execute(claim)
                    if await repository.complete_scheduled_publish(claim):
                        completed += 1
                except Exception as exc:
                    logger.exception(
                        "scheduled publish failed",
                        extra={"job_id": str(claim.id), "error_type": type(exc).__name__},
                    )
                    await repository.fail_scheduled_publish(
                        claim,
                        error_code=type(exc).__name__,
                        error_detail=redact_sensitive_text(str(exc)).content,
                    )
            return completed
        finally:
            await repository.close()

    return _run_database_poll("poll_scheduled_publishes", run)


@shared_task(
    name="cf_worker.poll_knowledge_imports",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def poll_knowledge_imports() -> int:
    async def run() -> int:
        settings = get_worker_settings()
        repository = PostgresOutboxRepository(settings)
        try:
            executor = KnowledgeImportExecutor(repository, settings)
            completed = 0
            for claim in await repository.claim_knowledge_imports():
                try:
                    await executor.execute(claim)
                    completed += 1
                except KnowledgeImportError as exc:
                    await repository.fail_knowledge_import(
                        claim, error_code=exc.code, permanent=True
                    )
                except Exception as exc:
                    logger.exception(
                        "knowledge import failed",
                        extra={"item_id": str(claim.id), "error_type": type(exc).__name__},
                    )
                    await repository.fail_knowledge_import(
                        claim, error_code=type(exc).__name__, permanent=False
                    )
            return completed
        finally:
            await repository.close()

    return _run_database_poll("poll_knowledge_imports", run)


__all__ = [
    "poll_outbox",
    "process_outbox_event",
    "purge_expired_visitor_profiles",
    "purge_expired_platform_onboarding_sessions",
    "poll_scheduled_publishes",
    "poll_knowledge_imports",
]
