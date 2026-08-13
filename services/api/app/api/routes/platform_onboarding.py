from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status

from app.api.content_import_schemas import (
    ContentImportCandidateEnvelope,
    ReviewContentCandidateRequest,
    UpdateContentCandidateRequest,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.platform_schemas import (
    CancelPlatformOnboardingRequest,
    ConfirmPlatformOnboardingRequest,
    GeneratePlatformOnboardingSuggestionsRequest,
    PlatformOnboardingImportStatusEnvelope,
    PlatformOnboardingSessionEnvelope,
    PlatformOnboardingSessionListEnvelope,
    StartPlatformOnboardingRequest,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.services.knowledge_import import (
    MAX_BATCH_BYTES,
    MAX_FILES,
    KnowledgeImportError,
    safe_file_name,
    validate_upload,
)
from app.services.knowledge_import_store import KnowledgeImportStore, PendingImport
from app.services.platform_onboarding import PlatformOnboardingService
from app.services.platform_store import PlatformActor

router = APIRouter(prefix="/platform/onboarding", tags=["Platform Onboarding"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _service(request: Request) -> PlatformOnboardingService:
    return PlatformOnboardingService(
        request.app.state.session_factory,
        request.app.state.settings,
    )


def _import_store(request: Request) -> KnowledgeImportStore:
    return KnowledgeImportStore(
        request.app.state.session_factory,
        request.app.state.settings,
    )


def _actor(principal: StaffPrincipal) -> PlatformActor:
    role = str(getattr(principal.role, "value", principal.role))
    if role != "platform_admin":
        raise ApiError(403, "FORBIDDEN", "仅平台管理员可操作企业开通会话")
    return PlatformActor(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        session_id=principal.session_id,
        role=role,
    )


@router.post(
    "",
    response_model=PlatformOnboardingSessionEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="startPlatformOnboarding",
)
async def start_onboarding(
    body: StartPlatformOnboardingRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformOnboardingSessionEnvelope:
    record = await _service(request).start(
        actor=_actor(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return PlatformOnboardingSessionEnvelope(data=record)


@router.put(
    "/{onboarding_id}/candidates/{candidate_id}",
    response_model=ContentImportCandidateEnvelope,
    operation_id="updatePlatformOnboardingCandidate",
)
async def update_onboarding_candidate(
    onboarding_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: UpdateContentCandidateRequest,
    request: Request,
    principal: StaffDependency,
) -> ContentImportCandidateEnvelope:
    return ContentImportCandidateEnvelope(
        data=await _service(request).update_content_candidate(
            actor=_actor(principal),
            onboarding_id=onboarding_id,
            candidate_id=candidate_id,
            body=body,
        )
    )


@router.post(
    "/{onboarding_id}/candidates/{candidate_id}/ignore",
    response_model=ContentImportCandidateEnvelope,
    operation_id="ignorePlatformOnboardingCandidate",
)
async def ignore_onboarding_candidate(
    onboarding_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: ReviewContentCandidateRequest,
    request: Request,
    principal: StaffDependency,
) -> ContentImportCandidateEnvelope:
    return ContentImportCandidateEnvelope(
        data=await _service(request).ignore_content_candidate(
            actor=_actor(principal),
            onboarding_id=onboarding_id,
            candidate_id=candidate_id,
            expected_version=body.expected_version,
        )
    )


@router.get(
    "",
    response_model=PlatformOnboardingSessionListEnvelope,
    operation_id="listPlatformOnboardingSessions",
)
async def list_onboarding(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlatformOnboardingSessionListEnvelope:
    records, total = await _service(request).list_sessions(
        actor=_actor(principal),
        limit=limit,
        offset=offset,
    )
    return PlatformOnboardingSessionListEnvelope(
        data=records,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{onboarding_id}",
    response_model=PlatformOnboardingSessionEnvelope,
    operation_id="getPlatformOnboardingSession",
)
async def get_onboarding(
    onboarding_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> PlatformOnboardingSessionEnvelope:
    return PlatformOnboardingSessionEnvelope(
        data=await _service(request).get_session(
            actor=_actor(principal),
            onboarding_id=onboarding_id,
        )
    )


@router.get(
    "/{onboarding_id}/imports",
    response_model=PlatformOnboardingImportStatusEnvelope,
    operation_id="getPlatformOnboardingImportStatus",
)
async def get_onboarding_import_status(
    onboarding_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> PlatformOnboardingImportStatusEnvelope:
    return PlatformOnboardingImportStatusEnvelope(
        data=await _service(request).get_import_status(
            actor=_actor(principal),
            onboarding_id=onboarding_id,
        )
    )


@router.post(
    "/{onboarding_id}/imports",
    response_model=PlatformOnboardingSessionEnvelope,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadPlatformOnboardingDocuments",
)
async def upload_onboarding_documents(
    onboarding_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    files: Annotated[list[UploadFile], File(...)],
) -> PlatformOnboardingSessionEnvelope:
    actor = _actor(principal)
    if not files or len(files) > MAX_FILES:
        raise ApiError(400, "IMPORT_FILE_COUNT", "每批仅允许上传 1 至 5 个文件")
    pending: list[PendingImport] = []
    total_bytes = 0
    try:
        for upload in files:
            file_name = safe_file_name(upload.filename)
            payload = await upload.read(10 * 1024 * 1024 + 1)
            total_bytes += len(payload)
            if total_bytes > MAX_BATCH_BYTES:
                raise KnowledgeImportError("IMPORT_BATCH_TOO_LARGE")
            pending.append(
                PendingImport(
                    file_name=file_name,
                    source_type=validate_upload(file_name, upload.content_type, payload),
                    content_type=upload.content_type or "application/octet-stream",
                    payload=payload,
                )
            )
    except KnowledgeImportError as exc:
        raise ApiError(400, exc.code, "文件不符合安全导入要求") from exc

    service = _service(request)
    target = await service.import_scope(actor=actor, onboarding_id=onboarding_id)
    batch = await _import_store(request).create_batch(
        scope=target.scope,
        items=pending,
        auto_publish=False,
        display_name=None,
        trace_id=request_id_ctx.get(),
    )
    record = await service.attach_import_batch(
        actor=actor,
        onboarding_id=onboarding_id,
        batch_id=batch.id,
        expected_version=target.version,
        trace_id=request_id_ctx.get(),
    )
    return PlatformOnboardingSessionEnvelope(data=record)


@router.post(
    "/{onboarding_id}/suggestions",
    response_model=PlatformOnboardingSessionEnvelope,
    operation_id="generatePlatformOnboardingSuggestions",
)
async def generate_onboarding_suggestions(
    onboarding_id: uuid.UUID,
    body: GeneratePlatformOnboardingSuggestionsRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformOnboardingSessionEnvelope:
    return PlatformOnboardingSessionEnvelope(
        data=await _service(request).generate_suggestions(
            actor=_actor(principal),
            onboarding_id=onboarding_id,
            expected_version=body.expected_version,
            trace_id=request_id_ctx.get(),
        )
    )


@router.post(
    "/{onboarding_id}/confirm",
    response_model=PlatformOnboardingSessionEnvelope,
    operation_id="confirmPlatformOnboarding",
)
async def confirm_onboarding(
    onboarding_id: uuid.UUID,
    body: ConfirmPlatformOnboardingRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformOnboardingSessionEnvelope:
    return PlatformOnboardingSessionEnvelope(
        data=await _service(request).confirm(
            actor=_actor(principal),
            onboarding_id=onboarding_id,
            body=body,
            trace_id=request_id_ctx.get(),
        )
    )


@router.post(
    "/{onboarding_id}/cancel",
    response_model=PlatformOnboardingSessionEnvelope,
    operation_id="cancelPlatformOnboarding",
)
async def cancel_onboarding(
    onboarding_id: uuid.UUID,
    body: CancelPlatformOnboardingRequest,
    request: Request,
    principal: StaffDependency,
) -> PlatformOnboardingSessionEnvelope:
    return PlatformOnboardingSessionEnvelope(
        data=await _service(request).cancel(
            actor=_actor(principal),
            onboarding_id=onboarding_id,
            expected_version=body.expected_version,
            reason=body.reason,
            trace_id=request_id_ctx.get(),
        )
    )


__all__ = ["router"]
