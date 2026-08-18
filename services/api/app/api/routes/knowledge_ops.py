from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status

from app.api.admin_schemas import (
    CreateKnowledgeDocumentRequest,
    KnowledgeDraftEnvelope,
    KnowledgePublishEnvelope,
    PutKnowledgeDocumentRequest,
)
from app.api.content_import_schemas import (
    BulkAcceptContentCandidatesRequest,
    ContentImportCandidateEnvelope,
    ContentImportCandidateListEnvelope,
    ContentImportCandidateRecord,
    ContentImportRunEnvelope,
    ContentImportRunListEnvelope,
    GenerateContentImportRequest,
    ReviewContentCandidateRequest,
    UpdateContentCandidateRequest,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.knowledge_import_schemas import (
    KnowledgeImportBatchEnvelope,
    KnowledgeImportBatchListEnvelope,
    RenameKnowledgeImportBatchRequest,
)
from app.api.knowledge_ops_schemas import (
    EvaluationJobEnvelope,
    FaqEnvelope,
    FaqListEnvelope,
    FaqWriteRequest,
    KnowledgeChunkListEnvelope,
    KnowledgeIndexJobEnvelope,
    KnowledgeIndexJobListEnvelope,
    KnowledgeVersionListEnvelope,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.admin_store import AdminScope, AdminStore
from app.services.catalog_store import CatalogScope, CatalogStore
from app.services.content_import_review import ContentImportReviewService
from app.services.knowledge_import import (
    KnowledgeImportError,
    safe_file_name,
    validate_upload,
)
from app.services.knowledge_import_store import (
    KnowledgeImportScope,
    KnowledgeImportStore,
    PendingImport,
)
from app.services.knowledge_ops_store import KnowledgeOpsScope, KnowledgeOpsStore

router = APIRouter(tags=["Knowledge Operations"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
_ADMIN_ROLES = {"company_admin", "platform_admin"}


def _scope(principal: StaffPrincipal) -> KnowledgeOpsScope:
    return KnowledgeOpsScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
    )


def _admin_scope(principal: StaffPrincipal) -> AdminScope:
    return AdminScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
    )


def _store(request: Request) -> KnowledgeOpsStore:
    return KnowledgeOpsStore(request.app.state.session_factory)


def _admin_store(request: Request) -> AdminStore:
    return AdminStore.from_runtime(
        session_factory=request.app.state.session_factory,
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
    )


def _import_store(request: Request) -> KnowledgeImportStore:
    return KnowledgeImportStore(request.app.state.session_factory, request.app.state.settings)


def _import_scope(principal: StaffPrincipal) -> KnowledgeImportScope:
    return KnowledgeImportScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
    )


def _catalog_scope(principal: StaffPrincipal) -> CatalogScope:
    if principal.company_id is None:
        raise ApiError(403, "COMPANY_SCOPE_REQUIRED", "请选择企业作用域后再执行此操作")
    return CatalogScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def _catalog_store(request: Request) -> CatalogStore:
    override = getattr(request.app.state, "catalog_store", None)
    if override is not None:
        return override
    base_url = getattr(request.app.state, "public_card_base_url", None)
    if base_url is None:
        origins = getattr(request.app.state.settings, "cors_allowed_origins", ())
        base_url = next(
            (
                origin
                for origin in origins
                if isinstance(origin, str)
                and origin.startswith(("https://", "http://localhost", "http://127.0.0.1"))
            ),
            "http://127.0.0.1:4173",
        )
    return CatalogStore(
        request.app.state.session_factory,
        public_card_base_url=base_url,
        allow_insecure_http=bool(
            getattr(request.app.state.settings, "allow_insecure_public_card_http", False)
        ),
    )


def _content_review_service(request: Request) -> ContentImportReviewService:
    override = getattr(request.app.state, "content_import_review_service", None)
    if override is not None:
        return override
    return ContentImportReviewService(
        request.app.state.session_factory,
        request.app.state.settings,
    )


def _require_category_accept_permission(
    principal: StaffPrincipal,
    category: str,
) -> None:
    permission = {
        "enterprise_profile": "company.write",
        "products": "catalog.write",
        "case_studies": "catalog.write",
        "faqs": "knowledge.write",
    }.get(category)
    if permission is None:
        raise ApiError(422, "UNCLASSIFIED_CANDIDATE", "未分类内容需先修改分类")
    _require_permission(principal, permission)


def _require_permission(principal: StaffPrincipal, *permissions: str) -> None:
    role = str(getattr(principal.role, "value", principal.role))
    if role in _ADMIN_ROLES:
        return
    granted = {str(value) for value in principal.permissions}
    if granted.intersection(permissions) or granted.intersection({"*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有执行此操作的权限")


@router.post(
    "/admin/knowledge/imports",
    response_model=KnowledgeImportBatchEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="createKnowledgeImport",
)
async def create_knowledge_import(
    request: Request,
    principal: StaffDependency,
    files: Annotated[list[UploadFile], File(...)],
    auto_publish: Annotated[bool, Form()] = False,
    display_name: Annotated[str | None, Form(max_length=120)] = None,
) -> KnowledgeImportBatchEnvelope:
    _require_permission(principal, "knowledge.write")
    if not files:
        raise ApiError(400, "IMPORT_FILE_COUNT", "请至少上传一个文件")
    pending: list[PendingImport] = []
    try:
        for upload in files:
            file_name = safe_file_name(upload.filename)
            payload = await upload.read()
            source_type = validate_upload(file_name, upload.content_type, payload)
            pending.append(
                PendingImport(
                    file_name=file_name,
                    source_type=source_type,
                    content_type=upload.content_type or "application/octet-stream",
                    payload=payload,
                )
            )
    except KnowledgeImportError as exc:
        raise ApiError(400, exc.code, "文件不符合安全导入要求") from exc
    result = await _import_store(request).create_batch(
        scope=_import_scope(principal),
        items=pending,
        auto_publish=auto_publish,
        display_name=display_name,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeImportBatchEnvelope(data=result)


@router.patch(
    "/admin/knowledge/imports/{batch_id}",
    response_model=KnowledgeImportBatchEnvelope,
    operation_id="renameKnowledgeImport",
)
async def rename_knowledge_import(
    batch_id: uuid.UUID,
    body: RenameKnowledgeImportBatchRequest,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeImportBatchEnvelope:
    _require_permission(principal, "knowledge.write")
    return KnowledgeImportBatchEnvelope(
        data=await _import_store(request).rename_batch(
            scope=_import_scope(principal),
            batch_id=batch_id,
            display_name=body.display_name,
            expected_version=body.expected_version,
            trace_id=request_id_ctx.get(),
        )
    )
@router.get(
    "/admin/knowledge/imports",
    response_model=KnowledgeImportBatchListEnvelope,
    operation_id="listKnowledgeImports",
)
async def list_knowledge_imports(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgeImportBatchListEnvelope:
    _require_permission(principal, "knowledge.read")
    records, total = await _import_store(request).list_batches(
        scope=_import_scope(principal), limit=limit, offset=offset
    )
    return KnowledgeImportBatchListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/admin/knowledge/imports/{batch_id}",
    response_model=KnowledgeImportBatchEnvelope,
    operation_id="getKnowledgeImport",
)
async def get_knowledge_import(
    batch_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeImportBatchEnvelope:
    _require_permission(principal, "knowledge.read")
    return KnowledgeImportBatchEnvelope(
        data=await _import_store(request).get_batch(
            scope=_import_scope(principal), batch_id=batch_id
        )
    )


@router.post(
    "/admin/content-import-runs",
    response_model=ContentImportRunEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="generateContentImportRun",
)
async def generate_content_import_run(
    body: GenerateContentImportRequest,
    request: Request,
    principal: StaffDependency,
) -> ContentImportRunEnvelope:
    _require_permission(principal, "knowledge.write")
    record = await _content_review_service(request).generate(
        scope=_admin_scope(principal),
        batch_id=body.batch_id,
        retry=body.retry,
        trace_id=request_id_ctx.get(),
    )
    return ContentImportRunEnvelope(data=record)


@router.get(
    "/admin/content-import-runs",
    response_model=ContentImportRunListEnvelope,
    operation_id="listContentImportRuns",
)
async def list_content_import_runs(
    request: Request,
    principal: StaffDependency,
) -> ContentImportRunListEnvelope:
    _require_permission(principal, "knowledge.read")
    records = await _content_review_service(request).list_runs(
        scope=_admin_scope(principal)
    )
    return ContentImportRunListEnvelope(data=records, total=len(records))


@router.get(
    "/admin/content-import-runs/{run_id}",
    response_model=ContentImportRunEnvelope,
    operation_id="getContentImportRun",
)
async def get_content_import_run(
    run_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> ContentImportRunEnvelope:
    _require_permission(principal, "knowledge.read")
    record = await _content_review_service(request).get_run(
        scope=_admin_scope(principal), run_id=run_id
    )
    return ContentImportRunEnvelope(data=record)


@router.patch(
    "/admin/content-import-candidates/{candidate_id}",
    response_model=ContentImportCandidateEnvelope,
    operation_id="updateContentImportCandidate",
)
async def update_content_import_candidate(
    candidate_id: uuid.UUID,
    body: UpdateContentCandidateRequest,
    request: Request,
    principal: StaffDependency,
) -> ContentImportCandidateEnvelope:
    _require_permission(principal, "knowledge.write")
    record = await _content_review_service(request).update_candidate(
        scope=_admin_scope(principal), candidate_id=candidate_id, body=body
    )
    return ContentImportCandidateEnvelope(data=record)


@router.post(
    "/admin/content-import-candidates/{candidate_id}/accept",
    response_model=ContentImportCandidateEnvelope,
    operation_id="acceptContentImportCandidate",
)
async def accept_content_import_candidate(
    candidate_id: uuid.UUID,
    body: ReviewContentCandidateRequest,
    request: Request,
    principal: StaffDependency,
) -> ContentImportCandidateEnvelope:
    service = _content_review_service(request)
    candidate = await service.get_candidate(
        scope=_admin_scope(principal), candidate_id=candidate_id
    )
    _require_category_accept_permission(principal, candidate.category)
    record = await service.accept_candidate(
        scope=_admin_scope(principal),
        catalog_scope=_catalog_scope(principal),
        candidate_id=candidate_id,
        expected_version=body.expected_version,
        apply_fields=body.apply_fields,
        confirm_sensitive_fields=body.confirm_sensitive_fields,
        admin=_admin_store(request),
        catalog=_catalog_store(request),
        trace_id=request_id_ctx.get(),
    )
    return ContentImportCandidateEnvelope(data=record)


@router.post(
    "/admin/content-import-candidates/{candidate_id}/ignore",
    response_model=ContentImportCandidateEnvelope,
    operation_id="ignoreContentImportCandidate",
)
async def ignore_content_import_candidate(
    candidate_id: uuid.UUID,
    body: ReviewContentCandidateRequest,
    request: Request,
    principal: StaffDependency,
) -> ContentImportCandidateEnvelope:
    _require_permission(principal, "knowledge.write")
    record = await _content_review_service(request).ignore_candidate(
        scope=_admin_scope(principal),
        candidate_id=candidate_id,
        expected_version=body.expected_version,
    )
    return ContentImportCandidateEnvelope(data=record)


@router.post(
    "/admin/content-import-candidates:bulk-accept",
    response_model=ContentImportCandidateListEnvelope,
    operation_id="bulkAcceptContentImportCandidates",
)
async def bulk_accept_content_import_candidates(
    body: BulkAcceptContentCandidatesRequest,
    request: Request,
    principal: StaffDependency,
) -> ContentImportCandidateListEnvelope:
    service = _content_review_service(request)
    records = []
    for item in body.candidates:
        candidate = await service.get_candidate(
            scope=_admin_scope(principal), candidate_id=item.id
        )
        if candidate.category == "enterprise_profile":
            raise ApiError(
                422,
                "SENSITIVE_CANDIDATE_REQUIRES_REVIEW",
                "企业资料候选必须逐条对比并确认，不能批量写入",
            )
        if candidate.confidence < 0.85 or not _candidate_is_complete(candidate):
            raise ApiError(
                422,
                "CANDIDATE_REQUIRES_REVIEW",
                "只有字段完整且置信度不低于 85% 的候选可以批量确认",
            )
        _require_category_accept_permission(principal, candidate.category)
        records.append(
            await service.accept_candidate(
                scope=_admin_scope(principal),
                catalog_scope=_catalog_scope(principal),
                candidate_id=item.id,
                expected_version=item.expected_version,
                apply_fields=item.apply_fields,
                confirm_sensitive_fields=False,
                admin=_admin_store(request),
                catalog=_catalog_store(request),
                trace_id=request_id_ctx.get(),
            )
        )
    return ContentImportCandidateListEnvelope(data=records, total=len(records))


def _candidate_is_complete(candidate: ContentImportCandidateRecord) -> bool:
    required = {
        "products": ("name", "summary", "detail"),
        "case_studies": ("title", "background", "solution", "result"),
        "faqs": ("question", "answer"),
    }.get(candidate.category)
    return bool(
        required
        and all(str(candidate.payload.get(field) or "").strip() for field in required)
    )


@router.get("/admin/faqs", response_model=FaqListEnvelope, operation_id="listAdminFaqs")
async def list_faqs(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FaqListEnvelope:
    _require_permission(principal, "knowledge.read", "knowledge.review")
    records, total = await _store(request).list_faqs(
        scope=_scope(principal), limit=limit, offset=offset
    )
    return FaqListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/admin/faqs",
    response_model=FaqEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminFaq",
)
async def create_faq(
    body: FaqWriteRequest,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.write")
    admin = _admin_store(request)
    document = await admin.create_document(
        scope=_admin_scope(principal),
        body=CreateKnowledgeDocumentRequest(title=body.question, source_type="faq"),
        trace_id=request_id_ctx.get(),
    )
    await admin.put_document_draft(
        scope=_admin_scope(principal),
        document_id=document.id,
        body=PutKnowledgeDocumentRequest(
            raw_text=body.answer,
            title=body.question,
            visibility=body.visibility,
            metadata={"source_label": "企业 FAQ"},
        ),
        trace_id=request_id_ctx.get(),
    )
    return FaqEnvelope(
        data=await _store(request).get_faq(scope=_scope(principal), document_id=document.id)
    )


@router.get(
    "/admin/faqs/{faq_id}",
    response_model=FaqEnvelope,
    operation_id="getAdminFaq",
)
async def get_faq(
    faq_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.read", "knowledge.review")
    return FaqEnvelope(
        data=await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    )


@router.patch(
    "/admin/faqs/{faq_id}",
    response_model=FaqEnvelope,
    operation_id="updateAdminFaq",
)
async def update_faq(
    faq_id: uuid.UUID,
    body: FaqWriteRequest,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.write")
    await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    await _admin_store(request).put_document_draft(
        scope=_admin_scope(principal),
        document_id=faq_id,
        body=PutKnowledgeDocumentRequest(
            raw_text=body.answer,
            title=body.question,
            visibility=body.visibility,
            metadata={"source_label": "企业 FAQ"},
        ),
        trace_id=request_id_ctx.get(),
    )
    return FaqEnvelope(
        data=await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    )


@router.delete(
    "/admin/faqs/{faq_id}",
    response_model=FaqEnvelope,
    operation_id="archiveAdminFaq",
)
async def archive_faq(
    faq_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> FaqEnvelope:
    _require_permission(principal, "knowledge.write")
    record = await _store(request).archive_faq(
        scope=_scope(principal), document_id=faq_id, trace_id=request_id_ctx.get()
    )
    return FaqEnvelope(data=record)


@router.post(
    "/admin/faqs/{faq_id}:publish",
    response_model=KnowledgePublishEnvelope,
    operation_id="publishAdminFaq",
)
async def publish_faq(
    faq_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgePublishEnvelope:
    _require_permission(principal, "knowledge.publish", "knowledge.review")
    await _store(request).get_faq(scope=_scope(principal), document_id=faq_id)
    result = await _admin_store(request).publish_document(
        scope=_admin_scope(principal),
        document_id=faq_id,
        version_id=None,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgePublishEnvelope(data=result)


@router.get(
    "/admin/knowledge/documents/{document_id}/versions",
    response_model=KnowledgeVersionListEnvelope,
    operation_id="listKnowledgeDocumentVersions",
)
async def list_document_versions(
    document_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeVersionListEnvelope:
    _require_permission(principal, "knowledge.read")
    records = await _store(request).list_versions(scope=_scope(principal), document_id=document_id)
    return KnowledgeVersionListEnvelope(data=records, total=len(records))


@router.post(
    "/admin/knowledge/documents/{document_id}/versions",
    response_model=KnowledgeDraftEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createKnowledgeDocumentVersion",
)
async def create_document_version(
    document_id: uuid.UUID,
    body: PutKnowledgeDocumentRequest,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeDraftEnvelope:
    _require_permission(principal, "knowledge.write")
    result = await _admin_store(request).put_document_draft(
        scope=_admin_scope(principal),
        document_id=document_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeDraftEnvelope(data=result)


@router.post(
    "/admin/knowledge/versions/{version_id}:publish",
    response_model=KnowledgePublishEnvelope,
    operation_id="publishKnowledgeVersion",
)
async def publish_version(
    version_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgePublishEnvelope:
    _require_permission(principal, "knowledge.publish", "knowledge.review")
    document_id = await _store(request).version_document(
        scope=_scope(principal), version_id=version_id
    )
    result = await _admin_store(request).publish_document(
        scope=_admin_scope(principal),
        document_id=document_id,
        version_id=version_id,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgePublishEnvelope(data=result)


@router.get(
    "/admin/knowledge/index-jobs",
    response_model=KnowledgeIndexJobListEnvelope,
    operation_id="listKnowledgeIndexJobs",
)
async def list_index_jobs(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    job_status: Annotated[
        str | None,
        Query(alias="status", pattern=r"^(pending|running|succeeded|failed)$"),
    ] = None,
) -> KnowledgeIndexJobListEnvelope:
    _require_permission(principal, "knowledge.read")
    records, total = await _store(request).list_index_jobs(
        scope=_scope(principal), limit=limit, offset=offset, status=job_status
    )
    return KnowledgeIndexJobListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/admin/knowledge/index-jobs/{job_id}:retry",
    response_model=KnowledgeIndexJobEnvelope,
    operation_id="retryKnowledgeIndexJob",
)
async def retry_index_job(
    job_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeIndexJobEnvelope:
    _require_permission(principal, "knowledge.publish", "knowledge.review")
    store = _store(request)
    target = await store.retry_target(scope=_scope(principal), job_id=job_id)
    await _admin_store(request).publish_document(
        scope=_admin_scope(principal),
        document_id=target.document_id,
        version_id=target.version_id,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeIndexJobEnvelope(
        data=await store.get_index_job(scope=_scope(principal), job_id=job_id)
    )


@router.get(
    "/admin/knowledge/chunks",
    response_model=KnowledgeChunkListEnvelope,
    operation_id="listKnowledgeChunks",
)
async def list_chunks(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    document_id: uuid.UUID | None = None,
) -> KnowledgeChunkListEnvelope:
    _require_permission(principal, "knowledge.read")
    records, total = await _store(request).list_chunks(
        scope=_scope(principal), limit=limit, offset=offset, document_id=document_id
    )
    return KnowledgeChunkListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/admin/knowledge:evaluate",
    response_model=EvaluationJobEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="evaluateKnowledge",
)
async def evaluate_knowledge(
    request: Request,
    principal: StaffDependency,
) -> EvaluationJobEnvelope:
    _require_permission(principal, "knowledge.review", "knowledge.publish")
    job = await _store(request).enqueue_evaluation(
        scope=_scope(principal), trace_id=request_id_ctx.get()
    )
    return EvaluationJobEnvelope(data=job)


__all__ = ["router"]
