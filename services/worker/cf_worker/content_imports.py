from __future__ import annotations

from app.core.config import Settings as ApiSettings
from app.services.admin_store import AdminScope
from app.services.content_import_review import ContentImportReviewService

from cf_worker.config import WorkerSettings
from cf_worker.domain import ClaimedContentImport
from cf_worker.repository import PostgresOutboxRepository


class ContentImportExecutor:
    def __init__(
        self,
        repository: PostgresOutboxRepository,
        settings: WorkerSettings,
    ) -> None:
        self._repository = repository
        self._settings = settings

    async def execute(self, claim: ClaimedContentImport) -> None:
        api_settings = ApiSettings(
            database_url=self._settings.database_url,
            field_encryption_key=self._settings.field_encryption_key,
            field_encryption_key_ref=self._settings.field_encryption_key_ref,
            field_encryption_previous_keys=self._settings.field_encryption_previous_keys,
        )
        service = ContentImportReviewService(
            self._repository.session_factory,
            api_settings,
        )
        await service.execute_claimed_run(
            scope=AdminScope(
                tenant_id=claim.tenant_id,
                company_id=claim.company_id,
                actor_user_id=claim.requested_by,
            ),
            run_id=claim.id,
            lock_token=claim.lock_token,
            trace_id=f"content-import-worker:{claim.id}:{claim.attempt}",
        )


__all__ = ["ContentImportExecutor"]
