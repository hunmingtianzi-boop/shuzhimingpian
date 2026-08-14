from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import replace

import pytest
from app.core.config import Settings as ApiSettings
from app.core.pii import PiiCipher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from cf_worker.config import WorkerSettings
from cf_worker.domain import ClaimedEvent, HandlerResult, NotificationIntent
from cf_worker.knowledge_imports import KnowledgeImportExecutor
from cf_worker.repository import PostgresOutboxRepository

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_WORKER_INTEGRATION") != "1",
        reason="set RUN_WORKER_INTEGRATION=1 against a disposable migrated database",
    ),
]


@pytest.mark.asyncio
async def test_real_knowledge_import_rls_lease_draft_cleanup_retry_and_idempotency() -> None:
    api_settings = ApiSettings()
    owner = create_async_engine(api_settings.migration_database_url, pool_pre_ping=True)
    app_engine = create_async_engine(api_settings.database_url, pool_pre_ping=True)
    worker_settings = WorkerSettings(
        worker_id="knowledge-import-integration",
        knowledge_import_batch_size=10,
        knowledge_import_lease_seconds=30,
        knowledge_import_max_attempts=2,
    )
    repository = PostgresOutboxRepository(worker_settings)
    cipher = PiiCipher.from_settings(worker_settings)
    plaintext = json.dumps(
        {"title": "集成导入", "raw_text": "仅生成待审核草稿", "visibility": "internal"},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    encrypted = cipher.encrypt(plaintext.decode())
    batch_ids = (uuid.uuid4(), uuid.uuid4())
    item_ids = (uuid.uuid4(), uuid.uuid4())
    document_ids: list[uuid.UUID] = []
    try:
        async with owner.begin() as connection:
            scopes = (
                await connection.execute(
                    text(
                        """
                        SELECT company.tenant_id, company.id, membership.user_id
                        FROM companies AS company
                        JOIN LATERAL (
                          SELECT user_id FROM memberships
                          WHERE tenant_id=company.tenant_id AND company_id=company.id
                          ORDER BY created_at LIMIT 1
                        ) AS membership ON true
                        ORDER BY company.created_at, company.id LIMIT 2
                        """
                    )
                )
            ).all()
            assert len(scopes) == 2
            for index, (tenant_id, company_id, user_id) in enumerate(scopes):
                await connection.execute(
                    text(
                        """
                        INSERT INTO knowledge_import_batches (
                          id, tenant_id, company_id, requested_by,
                          sequence_number, display_name, status,
                          total_items, pending_items, succeeded_items, failed_items
                        ) VALUES (
                          :batch, :tenant, :company, :user,
                          1, '集成测试导入 #001', 'pending', 1, 1, 0, 0
                        )
                        """
                    ),
                    {
                        "batch": batch_ids[index],
                        "tenant": tenant_id,
                        "company": company_id,
                        "user": user_id,
                    },
                )
                await connection.execute(
                    text(
                        """
                        INSERT INTO knowledge_import_items (
                          id, tenant_id, company_id, batch_id, file_name, source_type,
                          content_type, payload_ciphertext, payload_sha256, encryption_key_ref,
                          status, attempts, max_attempts, next_attempt_at
                        ) VALUES (
                          :item, :tenant, :company, :batch, 'bulk.csv', 'csv', 'text/csv',
                          :payload, :sha, :key_ref, 'pending', 0, 2, clock_timestamp()
                        )
                        """
                    ),
                    {
                        "batch": batch_ids[index],
                        "item": item_ids[index],
                        "tenant": tenant_id,
                        "company": company_id,
                        "payload": encrypted,
                        "sha": hashlib.sha256(plaintext).hexdigest(),
                        "key_ref": cipher.key_ref,
                    },
                )

        first_scope, second_scope = scopes
        async with app_engine.begin() as connection:
            await connection.execute(
                text(
                    "SELECT set_config('app.tenant_id', :tenant, true), "
                    "set_config('app.company_id', :company, true)"
                ),
                {"tenant": str(first_scope[0]), "company": str(first_scope[1])},
            )
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM knowledge_import_items WHERE id=:id"),
                    {"id": item_ids[1]},
                )
                == 0
            )

        claims = await repository.claim_knowledge_imports()
        claimed = {claim.id: claim for claim in claims}
        assert item_ids[0] in claimed and item_ids[1] in claimed
        executor = KnowledgeImportExecutor(repository, worker_settings)
        await executor.execute(claimed[item_ids[0]])
        await executor.execute(claimed[item_ids[0]])

        async with owner.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        """
                            SELECT item.status AS item_status, item.payload_ciphertext,
                                   item.document_id, item.version_id,
                                   document.status AS document_status,
                                   version.review_status,
                               (SELECT count(*) FROM knowledge_chunks
                                WHERE version_id=item.version_id) AS chunks
                        FROM knowledge_import_items AS item
                        JOIN knowledge_documents AS document ON document.id=item.document_id
                        JOIN knowledge_versions AS version ON version.id=item.version_id
                        WHERE item.id=:item
                        """
                    ),
                    {"item": item_ids[0]},
                )
            ).one()
            assert row.item_status == "completed"
            assert row.payload_ciphertext is None
            assert row.document_status == "draft" and row.review_status == "draft"
            assert row.chunks > 0
            document_ids.append(row.document_id)
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM knowledge_documents WHERE source_id=:source"),
                    {"source": f"import:{item_ids[0]}"},
                )
                == 1
            )

        with pytest.raises(RuntimeError, match="completed_import_result_mismatch"):
            await repository.complete_knowledge_import(
                claimed[item_ids[0]],
                row.document_id,
                row.version_id,
                published=True,
            )

        with pytest.raises(RuntimeError, match="stale_import_lease"):
            await repository.complete_knowledge_import(
                replace(claimed[item_ids[0]], attempts=0),
                row.document_id,
                row.version_id,
                published=False,
            )

        with pytest.raises(RuntimeError, match="stale_import_lease"):
            await repository.complete_knowledge_import(
                replace(claimed[item_ids[1]], lock_token=uuid.uuid4()),
                uuid.uuid4(),
                uuid.uuid4(),
                published=False,
            )

        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE knowledge_import_items "
                    "SET lease_expires_at=clock_timestamp()-interval '1 second' "
                    "WHERE id=:id"
                ),
                {"id": item_ids[1]},
            )
        with pytest.raises(RuntimeError, match="stale_import_lease"):
            await repository.complete_knowledge_import(
                claimed[item_ids[1]],
                uuid.uuid4(),
                uuid.uuid4(),
                published=False,
            )
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE knowledge_import_items "
                    "SET lease_expires_at=clock_timestamp()+interval '30 seconds' "
                    "WHERE id=:id"
                ),
                {"id": item_ids[1]},
            )

        assert (
            await repository.fail_knowledge_import(
                claimed[item_ids[1]], error_code="temporary", permanent=False
            )
            == "retry_scheduled"
        )
        async with owner.begin() as connection:
            retry_row = (
                await connection.execute(
                    text(
                        "SELECT status, payload_ciphertext FROM knowledge_import_items WHERE id=:id"
                    ),
                    {"id": item_ids[1]},
                )
            ).one()
            assert retry_row.status == "failed" and retry_row.payload_ciphertext is not None
            await connection.execute(
                text(
                    "UPDATE knowledge_import_items "
                    "SET next_attempt_at=clock_timestamp(), attempts=1 "
                    "WHERE id=:id"
                ),
                {"id": item_ids[1]},
            )
        retry_claim = next(
            claim for claim in await repository.claim_knowledge_imports() if claim.id == item_ids[1]
        )
        assert (
            await repository.fail_knowledge_import(
                retry_claim, error_code="exhausted", permanent=False
            )
            == "dead_letter"
        )
        async with owner.connect() as connection:
            dead = (
                await connection.execute(
                    text(
                        "SELECT status, payload_ciphertext FROM knowledge_import_items WHERE id=:id"
                    ),
                    {"id": item_ids[1]},
                )
            ).one()
            assert dead.status == "dead_letter" and dead.payload_ciphertext is None
    finally:
        async with owner.begin() as connection:
            await connection.execute(
                text("DELETE FROM knowledge_import_batches WHERE id = ANY(:ids)"),
                {"ids": list(batch_ids)},
            )
            if document_ids:
                await connection.execute(
                    text("DELETE FROM knowledge_documents WHERE id = ANY(:ids)"),
                    {"ids": document_ids},
                )
        await repository.close()
        await app_engine.dispose()
        await owner.dispose()


@pytest.mark.asyncio
async def test_worker_can_execute_global_profile_retention_purge() -> None:
    repository = PostgresOutboxRepository(WorkerSettings(worker_id="retention-worker"))
    try:
        assert await repository.purge_expired_visitor_profiles() >= 0
    finally:
        await repository.close()


@pytest.mark.asyncio
async def test_real_claim_scope_retry_crash_recovery_and_dead_letter() -> None:
    owner = create_async_engine(ApiSettings().migration_database_url, pool_pre_ping=True)
    worker_settings = WorkerSettings(
        outbox_batch_size=1,
        outbox_lease_seconds=30,
        outbox_heartbeat_seconds=5,
        outbox_max_attempts=3,
        outbox_backoff_base_seconds=5,
        outbox_backoff_max_seconds=20,
        worker_id="integration-worker",
    )
    repository = PostgresOutboxRepository(worker_settings)
    event_id = uuid.uuid4()
    try:
        async with owner.begin() as connection:
            scopes = (
                await connection.execute(
                    text(
                        """
                        SELECT tenant_id, id
                        FROM companies
                        ORDER BY created_at, id
                        LIMIT 2
                        """
                    )
                )
            ).all()
            assert len(scopes) == 2
            tenant_id, company_id = scopes[0]
            other_tenant_id, other_company_id = scopes[1]
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_events (
                      id, tenant_id, company_id, aggregate_type, aggregate_id,
                      event_type, payload, headers, deduplication_key, status, available_at
                    ) VALUES (
                      :id, :tenant_id, :company_id, 'integration', :aggregate_id,
                      'integration.test.v1', '{}'::jsonb, '{}'::jsonb,
                      :deduplication_key, 'pending', '2000-01-01T00:00:00Z'
                    )
                    """
                ),
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "aggregate_id": uuid.uuid4(),
                    "deduplication_key": f"worker-integration:{event_id}",
                },
            )

        first = (await repository.claim())[0]
        assert first.id == event_id
        assert first.attempt == 1
        assert await repository.load_leased(first) is not None
        wrong_scope = ClaimedEvent(
            id=first.id,
            tenant_id=other_tenant_id,
            company_id=other_company_id,
            lock_token=first.lock_token,
            event_type=first.event_type,
            attempt=first.attempt,
        )
        assert await repository.load_leased(wrong_scope) is None

        loaded = await repository.load_leased(first)
        assert loaded is not None
        assert (
            await repository.fail(
                loaded,
                error_code="integration_transient",
                permanent=False,
            )
            == "retry_scheduled"
        )
        async with owner.begin() as connection:
            status, delayed = (
                await connection.execute(
                    text(
                        """
                        SELECT status, available_at > clock_timestamp()
                        FROM outbox_events WHERE id = :id
                        """
                    ),
                    {"id": event_id},
                )
            ).one()
            assert status == "failed"
            assert delayed is True
            await connection.execute(
                text("UPDATE outbox_events SET available_at = '2000-01-01' WHERE id = :id"),
                {"id": event_id},
            )

        second = (await repository.claim())[0]
        assert second.id == event_id
        assert second.attempt == 2
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET locked_at = clock_timestamp() - interval '2 minutes',
                        lease_expires_at = clock_timestamp() - interval '1 minute'
                    WHERE id = :id
                    """
                ),
                {"id": event_id},
            )

        recovered = (await repository.claim())[0]
        assert recovered.id == event_id
        assert recovered.attempt == 3
        assert recovered.lock_token != second.lock_token
        assert await repository.load_leased(second) is None
        recovered_record = await repository.load_leased(recovered)
        assert recovered_record is not None
        assert (
            await repository.fail(
                recovered_record,
                error_code="integration_transient",
                permanent=False,
            )
            == "dead_letter"
        )
        async with owner.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT status FROM outbox_events WHERE id = :id"),
                    {"id": event_id},
                )
                == "dead_letter"
            )
    finally:
        async with owner.begin() as connection:
            await connection.execute(
                text("DELETE FROM outbox_events WHERE id = :id"),
                {"id": event_id},
            )
        await repository.close()
        await owner.dispose()


@pytest.mark.asyncio
async def test_real_completion_ledger_suppresses_duplicate_notification() -> None:
    owner = create_async_engine(ApiSettings().migration_database_url, pool_pre_ping=True)
    settings = WorkerSettings(
        outbox_batch_size=1,
        outbox_lease_seconds=30,
        outbox_heartbeat_seconds=5,
        worker_id="integration-worker",
    )
    repository = PostgresOutboxRepository(settings)
    event_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    recipient_id: uuid.UUID | None = None
    try:
        async with owner.begin() as connection:
            tenant_id, company_id, recipient_id = (
                await connection.execute(
                    text(
                        """
                        SELECT membership.tenant_id, membership.company_id, membership.user_id
                        FROM memberships AS membership
                        WHERE membership.company_id IS NOT NULL
                        ORDER BY membership.created_at, membership.id
                        LIMIT 1
                        """
                    )
                )
            ).one()
            await connection.execute(
                text(
                    """
                    INSERT INTO outbox_events (
                      id, tenant_id, company_id, aggregate_type, aggregate_id,
                      event_type, payload, headers, deduplication_key, status, available_at
                    ) VALUES (
                      :id, :tenant_id, :company_id, 'integration', :aggregate_id,
                      'integration.complete.v1', '{}'::jsonb, '{}'::jsonb,
                      :deduplication_key, 'pending', '2000-01-01T00:00:00Z'
                    )
                    """
                ),
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "aggregate_id": resource_id,
                    "deduplication_key": f"worker-complete:{event_id}",
                },
            )
        claim = (await repository.claim())[0]
        leased = await repository.load_leased(claim)
        assert leased is not None
        result = HandlerResult(
            handler_name="integration-handler-v1",
            notifications=(
                NotificationIntent(
                    recipient_user_id=recipient_id,
                    notification_type="worker_integration",
                    title="Worker integration",
                    body="Static non-PII integration notification.",
                    resource_type="worker_test",
                    resource_id=resource_id,
                ),
            ),
        )
        assert await repository.complete(leased, result) == "completed"

        replacement_token = uuid.uuid4()
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET status = 'processing', attempts = attempts + 1,
                        locked_at = clock_timestamp(), locked_by = 'duplicate-test',
                        lock_token = :token,
                        lease_expires_at = clock_timestamp() + interval '30 seconds'
                    WHERE id = :id
                    """
                ),
                {"id": event_id, "token": replacement_token},
            )
        duplicate_claim = ClaimedEvent(
            id=event_id,
            tenant_id=tenant_id,
            company_id=company_id,
            lock_token=replacement_token,
            event_type="integration.complete.v1",
            attempt=2,
        )
        duplicate = await repository.load_leased(duplicate_claim)
        assert duplicate is not None
        assert await repository.complete(duplicate, result) == "duplicate"

        async with owner.connect() as connection:
            notification_count = await connection.scalar(
                text(
                    """
                    SELECT count(*) FROM notifications
                    WHERE resource_type = 'worker_test' AND resource_id = :resource_id
                    """
                ),
                {"resource_id": resource_id},
            )
            delivery_count = await connection.scalar(
                text("SELECT count(*) FROM outbox_deliveries WHERE event_id = :event_id"),
                {"event_id": event_id},
            )
            assert notification_count == 1
            assert delivery_count == 1
    finally:
        async with owner.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM notifications WHERE resource_type = 'worker_test' "
                    "AND resource_id = :resource_id"
                ),
                {"resource_id": resource_id},
            )
            await connection.execute(
                text("DELETE FROM outbox_events WHERE id = :id"),
                {"id": event_id},
            )
        await repository.close()
        await owner.dispose()
