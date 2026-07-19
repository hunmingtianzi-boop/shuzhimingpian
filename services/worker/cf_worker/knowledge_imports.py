from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any

from app.core.pii import PiiCipher, PiiCipherError
from app.db.models import (
    ContentStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeImportItem,
    KnowledgeVersion,
    ReviewStatus,
    Visibility,
)
from app.services.admin_store import chunk_knowledge_text
from app.services.audit import append_audit
from app.services.knowledge_import import (
    KnowledgeImportError,
    decode_draft,
    validate_upload,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from cf_worker.config import WorkerSettings
from cf_worker.import_parser import parse_import_payload


@dataclass(frozen=True, slots=True)
class ClaimedKnowledgeImport:
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    batch_id: uuid.UUID
    lock_token: uuid.UUID
    file_name: str
    source_type: str
    content_type: str
    row_number: int | None
    auto_publish: bool
    payload_ciphertext: bytes
    payload_sha256: str
    encryption_key_ref: str
    attempts: int
    max_attempts: int
    requested_by: uuid.UUID


class KnowledgeImportExecutor:
    def __init__(self, repository: Any, settings: WorkerSettings) -> None:
        self._repository = repository
        self._settings = settings
        self._cipher = PiiCipher.from_settings(settings)

    async def execute(self, claim: ClaimedKnowledgeImport) -> None:
        try:
            plaintext = self._cipher.decrypt_bytes(claim.payload_ciphertext)
        except PiiCipherError as exc:
            raise KnowledgeImportError("IMPORT_DECRYPT_FAILED") from exc
        if hashlib.sha256(plaintext).hexdigest() != claim.payload_sha256:
            raise KnowledgeImportError("IMPORT_PAYLOAD_TAMPERED")
        # Imports queued before the raw-file pipeline used encrypted draft JSON.
        # Keep these queued records drainable during the rollout; new uploads are
        # always parsed here, never on the API request thread.
        if plaintext.startswith(b'{"title"'):
            drafts = [decode_draft(plaintext)]
        else:
            source_type = validate_upload(claim.file_name, claim.content_type, plaintext)
            drafts = parse_import_payload(
                source_type,
                claim.file_name,
                plaintext,
                timeout_seconds=self._settings.knowledge_import_parse_timeout_seconds,
            )
        if len(drafts) != 1:
            # A file is one auditable import item. CSV is intentionally rendered
            # as one document rather than silently spawning untracked documents.
            raise KnowledgeImportError("IMPORT_MULTIPLE_DOCUMENTS")
        draft = drafts[0]
        chunks = chunk_knowledge_text(draft.raw_text)
        (
            document_id,
            version_id,
            already_published,
        ) = await self._repository.create_knowledge_import_draft(claim, draft, chunks)
        if claim.auto_publish:
            if not already_published:
                await self._repository.publish_knowledge_import(claim, document_id, version_id)
            await self._repository.complete_knowledge_import(
                claim, document_id, version_id, published=True
            )
        else:
            await self._repository.complete_knowledge_import(
                claim, document_id, version_id, published=False
            )


async def create_draft(
    sessions: async_sessionmaker[AsyncSession],
    claim: ClaimedKnowledgeImport,
    draft: Any,
    chunks: tuple[str, ...],
) -> tuple[uuid.UUID, uuid.UUID, bool]:
    async with sessions() as session, session.begin():
        await session.execute(
            text(
                "SELECT set_config('app.tenant_id', :tenant, true), "
                "set_config('app.company_id', :company, true), "
                "set_config('app.user_id', '', true), set_config('app.session_id', '', true)"
            ),
            {"tenant": str(claim.tenant_id), "company": str(claim.company_id)},
        )
        current = await session.scalar(
            select(KnowledgeImportItem).where(KnowledgeImportItem.id == claim.id).with_for_update()
        )
        if current is None:
            raise RuntimeError("stale_import_lease")
        document_id = uuid.uuid5(uuid.NAMESPACE_URL, f"knowledge-import:{claim.id}")
        version_id = uuid.uuid5(uuid.NAMESPACE_URL, f"knowledge-import-version:{claim.id}")
        if current.status == "completed":
            if current.document_id == document_id and current.version_id == version_id:
                return document_id, version_id, bool(current.published_at)
            raise RuntimeError("completed_import_identity_mismatch")
        if current.status != "processing" or current.lock_token != claim.lock_token:
            raise RuntimeError("stale_import_lease")
        existing = await session.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        if existing is None:
            document = KnowledgeDocument(
                id=document_id,
                tenant_id=claim.tenant_id,
                company_id=claim.company_id,
                source_type=f"import_{claim.source_type}",
                source_id=f"import:{claim.id}",
                title=draft.title,
                status=ContentStatus.DRAFT,
                version=1,
            )
            session.add(document)
            version = KnowledgeVersion(
                id=version_id,
                tenant_id=claim.tenant_id,
                company_id=claim.company_id,
                document_id=document_id,
                version_number=1,
                raw_text=draft.raw_text,
                content_hash=hashlib.sha256(draft.raw_text.encode("utf-8")).hexdigest(),
                review_status=ReviewStatus.DRAFT,
            )
            session.add(version)
            await session.flush()
            session.add_all(
                [
                    KnowledgeChunk(
                        id=uuid.uuid5(
                            uuid.NAMESPACE_URL, f"knowledge-import-chunk:{claim.id}:{ordinal}"
                        ),
                        tenant_id=claim.tenant_id,
                        company_id=claim.company_id,
                        document_id=document_id,
                        version_id=version_id,
                        ordinal=ordinal,
                        title=draft.title,
                        text=value,
                        token_count=max(1, (len(value) + 1) // 2),
                        visibility=Visibility(draft.visibility),
                        is_active=False,
                        source_type=f"import_{claim.source_type}",
                        source_id=f"import:{claim.id}",
                        content_hash=hashlib.sha256(value.encode("utf-8")).hexdigest(),
                        metadata_json={"import_batch_id": str(claim.batch_id)},
                    )
                    for ordinal, value in enumerate(chunks)
                ]
            )
            await append_audit(
                session,
                tenant_id=claim.tenant_id,
                company_id=claim.company_id,
                actor_user_id=claim.requested_by,
                action="knowledge.import.draft.create",
                resource_type="knowledge_document",
                resource_id=document_id,
                trace_id=None,
                event_data={"batch_id": str(claim.batch_id), "source_type": claim.source_type},
            )
        current.document_id = document_id
        current.version_id = version_id
        current.parse_status = "completed"
        current.publish_status = "pending" if claim.auto_publish else "not_requested"
        await session.flush()
        # A retry after vector publication but before item completion must not
        # call publish_document again because its draft has already been consumed.
        version = await session.scalar(
            select(KnowledgeVersion).where(KnowledgeVersion.id == version_id)
        )
        return (
            document_id,
            version_id,
            bool(version and version.review_status == ReviewStatus.APPROVED),
        )


__all__ = ["ClaimedKnowledgeImport", "KnowledgeImportExecutor", "create_draft"]
