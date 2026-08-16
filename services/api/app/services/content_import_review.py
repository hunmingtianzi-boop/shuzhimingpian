from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import (
    ChatProviderConfig,
    OpenAICompatibleChatProvider,
    ProviderCredentials,
    StructuredOutputMode,
)
from app.api.admin_schemas import (
    CreateKnowledgeDocumentRequest,
    PutKnowledgeDocumentRequest,
    UpdateCompanyProfileRequest,
)
from app.api.catalog_schemas import CreateCaseStudyRequest, CreateProductRequest
from app.api.content_import_schemas import (
    ContentImportCandidateRecord,
    ContentImportRunRecord,
    UpdateContentCandidateRequest,
)
from app.api.errors import ApiError
from app.core.config import Settings
from app.db.models import (
    CaseStudy,
    ContentImportCandidate,
    ContentImportRun,
    KnowledgeDocument,
    KnowledgeImportBatch,
    KnowledgeImportBatchStatus,
    KnowledgeImportItem,
    KnowledgeVersion,
    Product,
)
from app.db.session import set_rls_context
from app.services.admin_store import AdminScope, AdminStore
from app.services.catalog_store import CatalogScope, CatalogStore
from app.services.content_classification import (
    ClassificationDocument,
    ContentClassification,
    classify_content_with_hard_gates,
)
from app.services.platform_llm_profiles import LLMRuntimeUnavailable, resolve_effective_chat_config


class ContentImportReviewService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings

    async def generate(
        self,
        *,
        scope: AdminScope,
        batch_id: uuid.UUID,
        retry: bool = False,
        trace_id: str | None,
    ) -> ContentImportRunRecord:
        documents = await self._documents(scope=scope, batch_id=batch_id)
        try:
            config = await resolve_effective_chat_config(self._sessions, self._settings)
        except LLMRuntimeUnavailable as exc:
            raise ApiError(
                503,
                "LLM_RUNTIME_UNAVAILABLE",
                "智能整理服务尚未配置，请联系平台管理员检查模型设置",
                details={"reason": exc.code},
            ) from exc
        run_id, should_execute = await self._prepare_run(
            scope=scope,
            batch_id=batch_id,
            provider=config.provider,
            model=config.model,
            retry=retry,
        )
        if not should_execute:
            return await self.get_run(scope=scope, run_id=run_id)
        provider = OpenAICompatibleChatProvider(
            ChatProviderConfig(
                base_url=config.base_url,
                model=config.model,
                provider_name=config.provider,
                timeout_seconds=min(config.timeout_seconds, 60),
                output_mode=StructuredOutputMode.JSON_OBJECT,
                thinking_mode=config.thinking,
                reasoning_effort=config.reasoning_effort,
                max_retries=config.max_retries,
            )
        )
        try:
            outcome = await classify_content_with_hard_gates(
                provider=provider,
                credentials=ProviderCredentials(api_key=config.api_key.get_secret_value()),
                documents=documents,
                max_tokens=min(config.max_output_tokens, 32_768),
                trace_id=trace_id,
            )
        except Exception:
            await self._finalize_failed_run(
                scope=scope,
                run_id=run_id,
                failure_code="classification_internal_error",
            )
            raise
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            run = await self._run(session, scope=scope, run_id=run_id, lock=True)
            run.status = outcome.status
            run.attempts = outcome.attempts
            run.failure_code = (outcome.failure_code or "")[:500] or None
            run.counts = _classification_counts(outcome.classification)
            run.completed_at = now
            await session.execute(
                delete(ContentImportCandidate).where(ContentImportCandidate.run_id == run_id)
            )
            session.add_all(
                _candidate_rows(
                    classification=outcome.classification,
                    run_id=run_id,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                )
            )
            await session.flush()
        return await self.get_run(scope=scope, run_id=run_id)

    async def _prepare_run(
        self,
        *,
        scope: AdminScope,
        batch_id: uuid.UUID,
        provider: str,
        model: str,
        retry: bool,
    ) -> tuple[uuid.UUID, bool]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            batch = await session.scalar(
                select(KnowledgeImportBatch)
                .where(
                    KnowledgeImportBatch.id == batch_id,
                    KnowledgeImportBatch.tenant_id == scope.tenant_id,
                    KnowledgeImportBatch.company_id == scope.company_id,
                )
                .with_for_update()
            )
            if batch is None:
                raise ApiError(404, "IMPORT_BATCH_NOT_FOUND", "资料导入批次不存在")
            run = await session.scalar(
                select(ContentImportRun)
                .where(
                    ContentImportRun.tenant_id == scope.tenant_id,
                    ContentImportRun.company_id == scope.company_id,
                    ContentImportRun.batch_id == batch_id,
                )
                .with_for_update()
            )
            if run is not None:
                _recover_stale_run(run)
                retryable_partial = (
                    run.status == "review"
                    and bool(run.failure_code)
                    and run.failure_code.startswith("classification_partial:")
                )
                if (run.status != "manual_required" and not retryable_partial) or not retry:
                    return run.id, False
                reviewed_candidate_id = await session.scalar(
                    select(ContentImportCandidate.id)
                    .where(
                        ContentImportCandidate.run_id == run.id,
                        ContentImportCandidate.status != "pending_review",
                    )
                    .limit(1)
                )
                if reviewed_candidate_id is not None:
                    raise ApiError(
                        409,
                        "CONTENT_IMPORT_REVIEW_STARTED",
                        "已有候选完成审核，不能覆盖式重试；请新建导入版本",
                    )
                await session.execute(
                    delete(ContentImportCandidate).where(ContentImportCandidate.run_id == run.id)
                )
                run.status = "processing"
                run.provider = provider
                run.model = model
                run.attempts = 0
                run.failure_code = None
                run.counts = {}
                run.completed_at = None
                await session.flush()
                return run.id, True

            run = ContentImportRun(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                batch_id=batch_id,
                requested_by=scope.actor_user_id,
                status="processing",
                provider=provider,
                model=model,
                attempts=0,
                counts={},
            )
            session.add(run)
            await session.flush()
            return run.id, True

    async def _finalize_failed_run(
        self, *, scope: AdminScope, run_id: uuid.UUID, failure_code: str
    ) -> None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            run = await self._run(session, scope=scope, run_id=run_id, lock=True)
            run.status = "manual_required"
            run.failure_code = failure_code[:500]
            run.completed_at = datetime.now(UTC)
            await session.flush()

    async def list_runs(self, *, scope: AdminScope) -> list[ContentImportRunRecord]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            runs = (
                await session.scalars(
                    select(ContentImportRun)
                    .where(
                        ContentImportRun.tenant_id == scope.tenant_id,
                        ContentImportRun.company_id == scope.company_id,
                    )
                    .order_by(ContentImportRun.created_at.desc())
                    .limit(50)
                )
            ).all()
            for run in runs:
                _recover_stale_run(run)
            await session.flush()
            return [await self._run_record(session, run) for run in runs]

    async def get_run(self, *, scope: AdminScope, run_id: uuid.UUID) -> ContentImportRunRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            run = await self._run(session, scope=scope, run_id=run_id)
            _recover_stale_run(run)
            await session.flush()
            return await self._run_record(session, run)

    async def get_candidate(
        self, *, scope: AdminScope, candidate_id: uuid.UUID
    ) -> ContentImportCandidateRecord:
        return await self._candidate_snapshot(scope=scope, candidate_id=candidate_id)

    async def update_candidate(
        self,
        *,
        scope: AdminScope,
        candidate_id: uuid.UUID,
        body: UpdateContentCandidateRequest,
    ) -> ContentImportCandidateRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            candidate = await self._candidate(
                session, scope=scope, candidate_id=candidate_id, lock=True
            )
            _require_pending(candidate)
            _require_version(candidate.version, body.expected_version)
            candidate.category = body.category
            candidate.payload = dict(body.payload)
            candidate.fingerprint = _fingerprint(
                body.category, body.payload, candidate.source_id, candidate.source_text
            )
            candidate.version += 1
            await session.flush()
            await session.refresh(candidate)
            return _candidate_record(candidate)

    async def ignore_candidate(
        self,
        *,
        scope: AdminScope,
        candidate_id: uuid.UUID,
        expected_version: int,
    ) -> ContentImportCandidateRecord:
        return await self._finish_candidate(
            scope=scope,
            candidate_id=candidate_id,
            expected_version=expected_version,
            status="ignored",
            target_type=None,
            target_id=None,
        )

    async def accept_candidate(
        self,
        *,
        scope: AdminScope,
        catalog_scope: CatalogScope,
        candidate_id: uuid.UUID,
        expected_version: int,
        apply_fields: list[str],
        admin: AdminStore,
        catalog: CatalogStore,
        trace_id: str | None,
        confirm_sensitive_fields: bool = False,
    ) -> ContentImportCandidateRecord:
        candidate = await self._candidate_snapshot(scope=scope, candidate_id=candidate_id)
        if candidate.status == "accepted":
            return candidate
        if candidate.status != "pending_review":
            raise ApiError(409, "CANDIDATE_NOT_PENDING", "该候选已经处理")
        _require_version(candidate.version, expected_version)
        payload = candidate.payload
        target_type: str
        target_id: uuid.UUID
        existing = await self._existing_target(
            scope=scope, category=candidate.category, candidate_id=candidate.id
        )
        if existing:
            target_type, target_id = existing
        elif candidate.category == "enterprise_profile":
            current = await admin.get_company_profile(scope=scope)
            allowed = {"company_name", "summary", "industry", "region", "website"}
            selected = set(apply_fields)
            if not selected or selected - allowed:
                raise ApiError(422, "INVALID_APPLY_FIELDS", "请明确勾选要更新的企业资料字段")
            values = {
                "name": current.name,
                "summary": current.summary,
                "industry": current.industry,
                "region": current.region,
                "website": current.website,
            }
            mapping = {
                "company_name": "name",
                "summary": "summary",
                "industry": "industry",
                "region": "region",
                "website": "website",
            }
            sensitive_changes = sorted(
                field
                for field in selected & {"company_name", "website"}
                if str(payload.get(field) or "").strip()
                != str(values[mapping[field]] or "").strip()
            )
            if sensitive_changes and not confirm_sensitive_fields:
                raise ApiError(
                    409,
                    "SENSITIVE_COMPANY_FIELDS_REQUIRE_CONFIRMATION",
                    "企业名称或官网将发生变化，请二次确认",
                    details={"fields": sensitive_changes},
                )
            for field in selected:
                values[mapping[field]] = str(payload.get(field) or "").strip() or None
            if not values["name"]:
                raise ApiError(422, "COMPANY_NAME_REQUIRED", "企业名称不能为空")
            try:
                body = UpdateCompanyProfileRequest(
                    **values,
                    logo_url=current.logo_url,
                    profile_personalization_policy_version=current.profile_personalization_policy_version,
                )
            except ValidationError as exc:
                raise ApiError(422, "CANDIDATE_PAYLOAD_INVALID", "企业资料字段不完整") from exc
            updated = await admin.update_company_profile(
                scope=scope,
                expected_version=current.version,
                body=body,
                trace_id=trace_id,
            )
            target_type, target_id = "company", updated.id
        elif candidate.category == "products":
            try:
                body = CreateProductRequest(
                    slug=_candidate_slug(candidate.id),
                    name=payload["name"],
                    category=payload["category"] or None,
                    summary=payload["summary"],
                    detail=payload["detail"],
                    audience=payload["audience"] or None,
                    price_boundary=payload["price_boundary"] or None,
                    settings={"content_import_candidate_id": str(candidate.id)},
                )
            except ValidationError as exc:
                raise ApiError(422, "CANDIDATE_PAYLOAD_INVALID", "核心业务字段不完整") from exc
            created = await catalog.create_product(
                scope=catalog_scope, body=body, trace_id=trace_id
            )
            target_type, target_id = "product", created.id
        elif candidate.category == "case_studies":
            try:
                body = CreateCaseStudyRequest(
                    slug=_candidate_slug(candidate.id),
                    title=payload["title"],
                    industry=payload["industry"] or None,
                    background=payload["background"],
                    solution=payload["solution"],
                    result=payload["result"],
                    client_display_name=payload["client_display_name"] or None,
                    settings={"content_import_candidate_id": str(candidate.id)},
                )
            except ValidationError as exc:
                raise ApiError(422, "CANDIDATE_PAYLOAD_INVALID", "案例字段不完整") from exc
            created = await catalog.create_case_study(
                scope=catalog_scope, body=body, trace_id=trace_id
            )
            target_type, target_id = "case_study", created.id
        elif candidate.category == "faqs":
            question = str(payload.get("question") or "").strip()
            answer = str(payload.get("answer") or "").strip()
            if not question or not answer:
                raise ApiError(422, "CANDIDATE_PAYLOAD_INVALID", "FAQ 问题和答案不能为空")
            document = await admin.create_document(
                scope=scope,
                body=CreateKnowledgeDocumentRequest(
                    title=question,
                    source_type="faq",
                    source_id=f"content-import:{candidate.id}",
                ),
                trace_id=trace_id,
            )
            await admin.put_document_draft(
                scope=scope,
                document_id=document.id,
                body=PutKnowledgeDocumentRequest(
                    raw_text=answer,
                    title=question,
                    visibility="public",
                    metadata={
                        "source_label": "资料智能整理",
                        "content_import_candidate_id": str(candidate.id),
                    },
                ),
                trace_id=trace_id,
            )
            target_type, target_id = "knowledge_document", document.id
        else:
            raise ApiError(422, "UNCLASSIFIED_CANDIDATE", "未分类内容需先修改分类")
        return await self._finish_candidate(
            scope=scope,
            candidate_id=candidate.id,
            expected_version=expected_version,
            status="accepted",
            target_type=target_type,
            target_id=target_id,
        )

    async def _documents(
        self, *, scope: AdminScope, batch_id: uuid.UUID
    ) -> list[ClassificationDocument]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            batch = await session.scalar(
                select(KnowledgeImportBatch).where(
                    KnowledgeImportBatch.id == batch_id,
                    KnowledgeImportBatch.tenant_id == scope.tenant_id,
                    KnowledgeImportBatch.company_id == scope.company_id,
                )
            )
            if batch is None:
                raise ApiError(404, "IMPORT_BATCH_NOT_FOUND", "资料导入批次不存在")
            if batch.status not in {
                KnowledgeImportBatchStatus.COMPLETED,
                KnowledgeImportBatchStatus.COMPLETED_WITH_ERRORS,
            }:
                raise ApiError(409, "IMPORT_BATCH_NOT_READY", "资料仍在解析，请稍后重试")
            rows = (
                await session.execute(
                    select(KnowledgeImportItem, KnowledgeVersion.raw_text)
                    .join(KnowledgeVersion, KnowledgeVersion.id == KnowledgeImportItem.version_id)
                    .where(
                        KnowledgeImportItem.batch_id == batch_id,
                        KnowledgeImportItem.tenant_id == scope.tenant_id,
                        KnowledgeImportItem.company_id == scope.company_id,
                    )
                    .order_by(KnowledgeImportItem.created_at, KnowledgeImportItem.id)
                )
            ).all()
            documents = [
                ClassificationDocument(
                    source_id=str(item.id),
                    file_name=item.file_name,
                    content=str(raw_text),
                )
                for item, raw_text in rows
                if str(raw_text).strip()
            ]
            if not documents:
                raise ApiError(409, "PARSED_DRAFT_MISSING", "没有可用于整理的解析文本")
            return documents

    async def _candidate_snapshot(
        self, *, scope: AdminScope, candidate_id: uuid.UUID
    ) -> ContentImportCandidateRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            return _candidate_record(
                await self._candidate(session, scope=scope, candidate_id=candidate_id)
            )

    async def _finish_candidate(
        self,
        *,
        scope: AdminScope,
        candidate_id: uuid.UUID,
        expected_version: int,
        status: str,
        target_type: str | None,
        target_id: uuid.UUID | None,
    ) -> ContentImportCandidateRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            candidate = await self._candidate(
                session, scope=scope, candidate_id=candidate_id, lock=True
            )
            if status == "accepted" and candidate.status == "accepted":
                return _candidate_record(candidate)
            _require_pending(candidate)
            _require_version(candidate.version, expected_version)
            candidate.status = status
            candidate.target_resource_type = target_type
            candidate.target_resource_id = target_id
            candidate.reviewed_by = scope.actor_user_id
            candidate.reviewed_at = datetime.now(UTC)
            candidate.version += 1
            await session.flush()
            await session.refresh(candidate)
            return _candidate_record(candidate)

    async def _existing_target(
        self,
        *,
        scope: AdminScope,
        category: str,
        candidate_id: uuid.UUID,
    ) -> tuple[str, uuid.UUID] | None:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            slug = _candidate_slug(candidate_id)
            if category == "products":
                target = await session.scalar(
                    select(Product.id).where(
                        Product.company_id == scope.company_id, Product.slug == slug
                    )
                )
                return ("product", target) if target else None
            if category == "case_studies":
                target = await session.scalar(
                    select(CaseStudy.id).where(
                        CaseStudy.company_id == scope.company_id, CaseStudy.slug == slug
                    )
                )
                return ("case_study", target) if target else None
            if category == "faqs":
                target = await session.scalar(
                    select(KnowledgeDocument.id).where(
                        KnowledgeDocument.company_id == scope.company_id,
                        KnowledgeDocument.source_type == "faq",
                        KnowledgeDocument.source_id == f"content-import:{candidate_id}",
                    )
                )
                return ("knowledge_document", target) if target else None
            return None

    async def _run(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        run_id: uuid.UUID,
        lock: bool = False,
    ) -> ContentImportRun:
        statement = select(ContentImportRun).where(
            ContentImportRun.id == run_id,
            ContentImportRun.tenant_id == scope.tenant_id,
            ContentImportRun.company_id == scope.company_id,
        )
        if lock:
            statement = statement.with_for_update()
        run = await session.scalar(statement)
        if run is None:
            raise ApiError(404, "CONTENT_IMPORT_RUN_NOT_FOUND", "智能整理任务不存在")
        return run

    async def _candidate(
        self,
        session: AsyncSession,
        *,
        scope: AdminScope,
        candidate_id: uuid.UUID,
        lock: bool = False,
    ) -> ContentImportCandidate:
        statement = select(ContentImportCandidate).where(
            ContentImportCandidate.id == candidate_id,
            ContentImportCandidate.tenant_id == scope.tenant_id,
            ContentImportCandidate.company_id == scope.company_id,
        )
        if lock:
            statement = statement.with_for_update()
        candidate = await session.scalar(statement)
        if candidate is None:
            raise ApiError(404, "CONTENT_IMPORT_CANDIDATE_NOT_FOUND", "智能整理候选不存在")
        return candidate

    async def _run_record(
        self, session: AsyncSession, run: ContentImportRun
    ) -> ContentImportRunRecord:
        candidates = (
            await session.scalars(
                select(ContentImportCandidate)
                .where(ContentImportCandidate.run_id == run.id)
                .order_by(ContentImportCandidate.created_at, ContentImportCandidate.id)
            )
        ).all()
        return ContentImportRunRecord(
            id=run.id,
            batch_id=run.batch_id,
            status=run.status,
            provider=run.provider,
            model=run.model,
            attempts=run.attempts,
            failure_code=run.failure_code,
            counts={str(key): int(value) for key, value in run.counts.items()},
            candidates=[_candidate_record(candidate) for candidate in candidates],
            completed_at=run.completed_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    @staticmethod
    async def _set_scope(session: AsyncSession, scope: AdminScope) -> None:
        await set_rls_context(session, tenant_id=scope.tenant_id, company_id=scope.company_id)


def _candidate_rows(
    *,
    classification: ContentClassification,
    run_id: uuid.UUID,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
) -> list[ContentImportCandidate]:
    rows: list[ContentImportCandidate] = []
    for category in (
        "enterprise_profile",
        "products",
        "case_studies",
        "faqs",
        "unclassified",
    ):
        for item in getattr(classification, category):
            dumped = item.model_dump()
            meta = dumped.pop("meta")
            fingerprint = _fingerprint(category, dumped, meta["source_id"], meta["source_text"])
            rows.append(
                ContentImportCandidate(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    company_id=company_id,
                    run_id=run_id,
                    category=category,
                    payload=dumped,
                    source_id=meta["source_id"],
                    source_text=meta["source_text"],
                    confidence=meta["confidence"],
                    fingerprint=fingerprint,
                    status="pending_review",
                    version=1,
                )
            )
    return rows


def _classification_counts(classification: ContentClassification) -> dict[str, int]:
    return {
        category: len(getattr(classification, category))
        for category in (
            "enterprise_profile",
            "products",
            "case_studies",
            "faqs",
            "unclassified",
        )
    }


def _fingerprint(
    category: str,
    payload: dict[str, Any],
    source_id: str,
    source_text: str,
) -> str:
    wire = json.dumps(
        [category, payload, source_id, source_text],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(wire.encode()).hexdigest()


def _recover_stale_run(run: ContentImportRun) -> None:
    if run.status != "processing":
        return
    updated_at = run.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    if updated_at >= datetime.now(UTC) - timedelta(minutes=10):
        return
    run.status = "manual_required"
    run.failure_code = "classification_interrupted"
    run.completed_at = datetime.now(UTC)


def _candidate_slug(candidate_id: uuid.UUID) -> str:
    return f"import-{candidate_id.hex}"


def _candidate_record(candidate: ContentImportCandidate) -> ContentImportCandidateRecord:
    return ContentImportCandidateRecord(
        id=candidate.id,
        run_id=candidate.run_id,
        category=candidate.category,
        payload=dict(candidate.payload),
        source_id=candidate.source_id,
        source_text=candidate.source_text,
        confidence=candidate.confidence,
        status=candidate.status,
        target_resource_type=candidate.target_resource_type,
        target_resource_id=candidate.target_resource_id,
        version=candidate.version,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


def _require_pending(candidate: ContentImportCandidate) -> None:
    if candidate.status != "pending_review":
        raise ApiError(409, "CANDIDATE_NOT_PENDING", "该候选已经处理")


def _require_version(current: int, expected: int) -> None:
    if current != expected:
        raise ApiError(
            409,
            "VERSION_CONFLICT",
            "候选已被其他操作更新，请刷新后重试",
            details={"current_version": current},
        )


__all__ = ["ContentImportReviewService"]
