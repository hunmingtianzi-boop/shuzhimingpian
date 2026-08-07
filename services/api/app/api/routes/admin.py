from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.admin_schemas import (
    CardProfileEnvelope,
    CompanyProfileEnvelope,
    CreateKnowledgeDocumentRequest,
    EnterpriseSetupEnvelope,
    EnterpriseSetupResult,
    KnowledgeDocumentDetailEnvelope,
    KnowledgeDocumentEnvelope,
    KnowledgeDocumentListEnvelope,
    KnowledgeDraftEnvelope,
    KnowledgePublishEnvelope,
    PublishKnowledgeDocumentRequest,
    PutKnowledgeDocumentRequest,
    UpdateCardRequest,
    UpdateCompanyProfileRequest,
)
from app.api.catalog_schemas import (
    CardComposerDefaultEnvelope,
    CaseStudyEnvelope,
    CaseStudyListEnvelope,
    CreateCardRequest,
    CreateCaseStudyRequest,
    CreateForbiddenTopicRequest,
    CreateProductRequest,
    EnterpriseTemplateEnvelope,
    ForbiddenTopicEnvelope,
    ForbiddenTopicListEnvelope,
    ManagedCardEnvelope,
    ManagedCardListEnvelope,
    ProductEnvelope,
    ProductListEnvelope,
    UpdateCardComposerDefaultRequest,
    UpdateCaseStudyRequest,
    UpdateEnterpriseTemplateRequest,
    UpdateForbiddenTopicRequest,
    UpdateManagedCardRequest,
    UpdateProductRequest,
)
from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.scheduled_publish_schemas import (
    ScheduledPublishJobEnvelope,
    ScheduledPublishJobListEnvelope,
    SchedulePublishRequest,
)
from app.api.wecom_schemas import (
    WeComCardContactWayEnvelope,
    WeComCardContactWayRecord,
)
from app.core.request_context import request_id_ctx
from app.core.tokens import StaffPrincipal
from app.db.models import CardKind, ContentStatus, ScheduledPublishResourceType
from app.integrations.wecom import (
    WeComClient,
    WeComConfigurationError,
    WeComProviderError,
)
from app.services.admin_store import AdminScope, AdminStore
from app.services.catalog_knowledge import CatalogKnowledgeSynchronizer
from app.services.catalog_store import CatalogScope, CatalogStore, require_version
from app.services.scheduled_publish_store import ScheduledPublishStore
from app.services.wecom_store import WeComCardContactRecord, WeComStore

router = APIRouter(prefix="/admin", tags=["Admin Content"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]
IfMatchDependency = Annotated[str, Header(alias="If-Match")]

_ADMIN_ROLES = {"company_admin", "platform_admin"}
_PERMISSIONS: dict[str, set[str]] = {
    "company.read": {
        "company.profile.read",
        "company.profile.write",
        "company.manage",
    },
    "company.write": {"company.profile.write", "company.manage"},
    "card.read": {"card.read", "card.write", "card.manage"},
    "card.write": {"card.write", "card.manage"},
    "catalog.read": {
        "catalog.read",
        "catalog.write",
        "catalog.publish",
        "catalog.manage",
        "product.read",
        "product.write",
        "product.publish",
        "case_study.read",
        "case_study.write",
        "case_study.publish",
    },
    "catalog.write": {
        "catalog.write",
        "catalog.manage",
        "product.write",
        "case_study.write",
    },
    "catalog.publish": {
        "catalog.publish",
        "catalog.manage",
        "product.publish",
        "case_study.publish",
    },
    "forbidden_topic.read": {
        "forbidden_topic.read",
        "forbidden_topic.write",
        "forbidden_topic.manage",
    },
    "forbidden_topic.write": {
        "forbidden_topic.write",
        "forbidden_topic.manage",
    },
    "knowledge.read": {
        "knowledge.read",
        "knowledge.write",
        "knowledge.review",
        "knowledge.publish",
        "knowledge.manage",
    },
    "knowledge.write": {
        "knowledge.write",
        "knowledge.review",
        "knowledge.manage",
    },
    "knowledge.publish": {
        "knowledge.publish",
        "knowledge.review",
        "knowledge.manage",
    },
}


def _store(request: Request) -> AdminStore:
    return AdminStore.from_runtime(
        session_factory=request.app.state.session_factory,
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
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


def _catalog_knowledge(request: Request) -> CatalogKnowledgeSynchronizer:
    override = getattr(request.app.state, "catalog_knowledge_synchronizer", None)
    if override is not None:
        return override
    return CatalogKnowledgeSynchronizer.from_runtime(
        session_factory=request.app.state.session_factory,
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
    )


def _scheduled_publish_store(request: Request) -> ScheduledPublishStore:
    override = getattr(request.app.state, "scheduled_publish_store", None)
    if override is not None:
        return override
    return ScheduledPublishStore(request.app.state.session_factory)


def _wecom_store(request: Request) -> WeComStore:
    return WeComStore(request.app.state.session_factory, request.app.state.settings)


def _wecom_client(request: Request) -> WeComClient:
    return WeComClient(
        settings=request.app.state.settings,
        http_client=request.app.state.http_client,
        redis=getattr(request.app.state, "redis", None),
    )


def _wecom_contact_record(record: WeComCardContactRecord) -> WeComCardContactWayRecord:
    return WeComCardContactWayRecord(
        id=record.id,
        card_id=record.card_id,
        owner_user_id=record.owner_user_id,
        qr_code_url=record.qr_code_url,
        provisioned_at=record.provisioned_at,
    )


def _scope(principal: StaffPrincipal) -> AdminScope:
    if principal.company_id is None:
        raise ApiError(403, "COMPANY_SCOPE_REQUIRED", "请选择企业作用域后再执行此操作")
    return AdminScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
    )


def _catalog_scope(principal: StaffPrincipal) -> CatalogScope:
    if principal.company_id is None:
        raise ApiError(403, "COMPANY_SCOPE_REQUIRED", "请选择企业作用域后再执行此操作")
    role = getattr(principal.role, "value", principal.role)
    return CatalogScope(
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        actor_user_id=principal.user_id,
        role=str(role),
    )


def _require_permission(principal: StaffPrincipal, permission: str) -> None:
    role = getattr(principal.role, "value", principal.role)
    if str(role) in _ADMIN_ROLES:
        return
    granted = {str(value) for value in principal.permissions}
    allowed = _PERMISSIONS.get(permission, {permission})
    if granted.intersection(allowed) or granted.intersection({"*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有执行此操作的权限")


def _require_any_permission(principal: StaffPrincipal, *permissions: str) -> None:
    role = getattr(principal.role, "value", principal.role)
    if str(role) in _ADMIN_ROLES:
        return
    granted = {str(value) for value in principal.permissions}
    allowed = set().union(*(_PERMISSIONS.get(item, {item}) for item in permissions))
    if granted.intersection(allowed) or granted.intersection({"*", "admin:*"}):
        return
    raise ApiError(403, "FORBIDDEN", "当前账号没有执行此操作的权限")


def parse_if_match(value: str) -> int:
    candidate = value.strip()
    if candidate.startswith("W/"):
        candidate = candidate[2:].strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] == '"':
        candidate = candidate[1:-1]
    if not candidate.isascii() or not candidate.isdigit():
        raise ApiError(400, "INVALID_IF_MATCH", "If-Match 必须是资源版本号")
    version = int(candidate)
    if version < 1:
        raise ApiError(400, "INVALID_IF_MATCH", "If-Match 必须是正整数版本号")
    return version


def _set_etag(response: Response, version: int) -> None:
    response.headers["ETag"] = f'"{version}"'


@router.get(
    "/company/profile",
    response_model=CompanyProfileEnvelope,
    operation_id="getCompanyProfile",
)
async def get_company_profile(
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> CompanyProfileEnvelope:
    _require_permission(principal, "company.read")
    profile = await _store(request).get_company_profile(scope=_scope(principal))
    _set_etag(response, profile.version)
    return CompanyProfileEnvelope(data=profile)


@router.put(
    "/company/profile",
    response_model=CompanyProfileEnvelope,
    operation_id="updateCompanyProfile",
)
async def update_company_profile(
    body: UpdateCompanyProfileRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> CompanyProfileEnvelope:
    _require_permission(principal, "company.write")
    profile = await _store(request).update_company_profile(
        scope=_scope(principal),
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, profile.version)
    return CompanyProfileEnvelope(data=profile)


@router.get(
    "/card",
    response_model=CardProfileEnvelope,
    operation_id="getAdminCard",
)
async def get_card(
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> CardProfileEnvelope:
    _require_permission(principal, "card.read")
    card = await _store(request).get_card(scope=_scope(principal))
    _set_etag(response, card.version)
    return CardProfileEnvelope(data=card)


@router.put(
    "/card",
    response_model=CardProfileEnvelope,
    operation_id="updateAdminCard",
)
async def update_card(
    body: UpdateCardRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> CardProfileEnvelope:
    _require_permission(principal, "card.write")
    card = await _store(request).update_card(
        scope=_scope(principal),
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, card.version)
    return CardProfileEnvelope(data=card)


@router.post(
    "/setup/complete",
    response_model=EnterpriseSetupEnvelope,
    operation_id="completeEnterpriseSetup",
)
async def complete_enterprise_setup(
    request: Request,
    principal: StaffDependency,
) -> EnterpriseSetupEnvelope:
    _require_permission(principal, "company.write")
    _require_permission(principal, "card.write")
    company, card = await _store(request).complete_enterprise_setup(
        scope=_scope(principal),
        trace_id=request_id_ctx.get(),
    )
    return EnterpriseSetupEnvelope(
        data=EnterpriseSetupResult(completed=True, company=company, card=card)
    )


@router.get(
    "/knowledge/documents",
    response_model=KnowledgeDocumentListEnvelope,
    operation_id="listKnowledgeDocuments",
)
async def list_knowledge_documents(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    selectable_faq: bool = False,
) -> KnowledgeDocumentListEnvelope:
    _require_permission(principal, "knowledge.read")
    records, total = await _store(request).list_documents(
        scope=_scope(principal),
        limit=limit,
        selectable_faq=selectable_faq,
    )
    return KnowledgeDocumentListEnvelope(data=records, total=total)


@router.get(
    "/knowledge/documents/{document_id}",
    response_model=KnowledgeDocumentDetailEnvelope,
    operation_id="getKnowledgeDocument",
)
async def get_knowledge_document(
    document_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeDocumentDetailEnvelope:
    _require_permission(principal, "knowledge.read")
    detail = await _store(request).get_document_detail(
        scope=_scope(principal),
        document_id=document_id,
    )
    return KnowledgeDocumentDetailEnvelope(data=detail)


@router.post(
    "/knowledge/documents",
    response_model=KnowledgeDocumentEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createKnowledgeDocument",
)
async def create_knowledge_document(
    body: CreateKnowledgeDocumentRequest,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeDocumentEnvelope:
    _require_permission(principal, "knowledge.write")
    record = await _store(request).create_document(
        scope=_scope(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeDocumentEnvelope(data=record)


@router.put(
    "/knowledge/documents/{document_id}",
    response_model=KnowledgeDraftEnvelope,
    operation_id="putKnowledgeDocumentDraft",
)
async def put_knowledge_document_draft(
    document_id: uuid.UUID,
    body: PutKnowledgeDocumentRequest,
    request: Request,
    principal: StaffDependency,
) -> KnowledgeDraftEnvelope:
    _require_permission(principal, "knowledge.write")
    result = await _store(request).put_document_draft(
        scope=_scope(principal),
        document_id=document_id,
        body=body,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgeDraftEnvelope(data=result)


@router.post(
    "/knowledge/documents/{document_id}/publish",
    response_model=KnowledgePublishEnvelope,
    operation_id="publishKnowledgeDocument",
)
async def publish_knowledge_document(
    document_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    body: PublishKnowledgeDocumentRequest | None = None,
) -> KnowledgePublishEnvelope:
    _require_permission(principal, "knowledge.publish")
    result = await _store(request).publish_document(
        scope=_scope(principal),
        document_id=document_id,
        version_id=body.version_id if body else None,
        trace_id=request_id_ctx.get(),
    )
    return KnowledgePublishEnvelope(data=result)


@router.post(
    "/knowledge/documents/{document_id}:schedule-publish",
    response_model=ScheduledPublishJobEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="scheduleKnowledgeDocumentPublish",
)
async def schedule_knowledge_document_publish(
    document_id: uuid.UUID,
    body: SchedulePublishRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ScheduledPublishJobEnvelope:
    _require_permission(principal, "knowledge.publish")
    job = await _scheduled_publish_store(request).schedule(
        scope=_scope(principal),
        resource_type=ScheduledPublishResourceType.KNOWLEDGE_DOCUMENT,
        resource_id=document_id,
        expected_version=parse_if_match(if_match),
        knowledge_version_id=body.version_id,
        scheduled_at=body.scheduled_at,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, job.version)
    return ScheduledPublishJobEnvelope(data=job)


@router.get(
    "/products",
    response_model=ProductListEnvelope,
    operation_id="listAdminProducts",
)
async def list_products(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    content_status: Annotated[ContentStatus | None, Query(alias="status")] = None,
    card_kind: Annotated[CardKind | None, Query(alias="card_kind")] = None,
) -> ProductListEnvelope:
    _require_permission(principal, "catalog.read")
    records, total = await _catalog_store(request).list_products(
        scope=_catalog_scope(principal),
        limit=limit,
        offset=offset,
        status=content_status,
        card_kind=card_kind,
    )
    return ProductListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/products",
    response_model=ProductEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminProduct",
)
async def create_product(
    body: CreateProductRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> ProductEnvelope:
    _require_permission(principal, "catalog.write")
    record = await _catalog_store(request).create_product(
        scope=_catalog_scope(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ProductEnvelope(data=record)


@router.get(
    "/products/{product_id}",
    response_model=ProductEnvelope,
    operation_id="getAdminProduct",
)
async def get_product(
    product_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> ProductEnvelope:
    _require_permission(principal, "catalog.read")
    record = await _catalog_store(request).get_product(
        scope=_catalog_scope(principal),
        product_id=product_id,
    )
    _set_etag(response, record.version)
    return ProductEnvelope(data=record)


@router.put(
    "/products/{product_id}",
    response_model=ProductEnvelope,
    operation_id="updateAdminProduct",
)
@router.patch(
    "/products/{product_id}",
    response_model=ProductEnvelope,
    operation_id="patchAdminProduct",
)
async def update_product(
    product_id: uuid.UUID,
    body: UpdateProductRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ProductEnvelope:
    _require_permission(principal, "catalog.write")
    record = await _catalog_store(request).update_product(
        scope=_catalog_scope(principal),
        product_id=product_id,
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ProductEnvelope(data=record)


@router.post(
    "/products/{product_id}/publish",
    response_model=ProductEnvelope,
    operation_id="publishAdminProduct",
)
@router.post(
    "/products/{product_id}:publish",
    response_model=ProductEnvelope,
    operation_id="publishAdminProductContractAlias",
)
async def publish_product(
    product_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ProductEnvelope:
    _require_permission(principal, "catalog.publish")
    expected_version = parse_if_match(if_match)
    catalog_scope = _catalog_scope(principal)
    catalog = _catalog_store(request)
    draft = await catalog.get_product(scope=catalog_scope, product_id=product_id)
    require_version(draft.version, expected_version)
    await _catalog_knowledge(request).sync_product(
        scope=_scope(principal),
        product=draft,
        trace_id=request_id_ctx.get(),
    )
    record = await catalog.publish_product(
        scope=catalog_scope,
        product_id=product_id,
        expected_version=expected_version,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ProductEnvelope(data=record)


@router.post(
    "/products/{product_id}:schedule-publish",
    response_model=ScheduledPublishJobEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="scheduleAdminProductPublish",
)
async def schedule_product_publish(
    product_id: uuid.UUID,
    body: SchedulePublishRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ScheduledPublishJobEnvelope:
    _require_permission(principal, "catalog.publish")
    if body.version_id is not None:
        raise ApiError(422, "VERSION_ID_NOT_ALLOWED", "产品定时发布不能指定知识版本")
    expected_version = parse_if_match(if_match)
    scope = _catalog_scope(principal)
    draft = await _catalog_store(request).get_product(scope=scope, product_id=product_id)
    require_version(draft.version, expected_version)
    await _catalog_knowledge(request).sync_product(
        scope=_scope(principal), product=draft, trace_id=request_id_ctx.get()
    )
    job = await _scheduled_publish_store(request).schedule(
        scope=_scope(principal),
        resource_type=ScheduledPublishResourceType.PRODUCT,
        resource_id=product_id,
        expected_version=expected_version,
        scheduled_at=body.scheduled_at,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, job.version)
    return ScheduledPublishJobEnvelope(data=job)


@router.post(
    "/products/{product_id}/archive",
    response_model=ProductEnvelope,
    operation_id="archiveAdminProduct",
)
async def archive_product(
    product_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ProductEnvelope:
    _require_permission(principal, "catalog.publish")
    record = await _catalog_store(request).archive_product(
        scope=_catalog_scope(principal),
        product_id=product_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ProductEnvelope(data=record)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteAdminProduct",
)
async def delete_product(
    product_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> None:
    _require_permission(principal, "catalog.write")
    await _catalog_store(request).delete_product(
        scope=_catalog_scope(principal),
        product_id=product_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )


@router.get(
    "/case-studies",
    response_model=CaseStudyListEnvelope,
    operation_id="listAdminCaseStudies",
)
@router.get(
    "/cases",
    response_model=CaseStudyListEnvelope,
    operation_id="listAdminCases",
)
async def list_case_studies(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    content_status: Annotated[ContentStatus | None, Query(alias="status")] = None,
) -> CaseStudyListEnvelope:
    _require_permission(principal, "catalog.read")
    records, total = await _catalog_store(request).list_case_studies(
        scope=_catalog_scope(principal),
        limit=limit,
        offset=offset,
        status=content_status,
    )
    return CaseStudyListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/case-studies",
    response_model=CaseStudyEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminCaseStudy",
)
@router.post(
    "/cases",
    response_model=CaseStudyEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminCase",
)
async def create_case_study(
    body: CreateCaseStudyRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> CaseStudyEnvelope:
    _require_permission(principal, "catalog.write")
    record = await _catalog_store(request).create_case_study(
        scope=_catalog_scope(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return CaseStudyEnvelope(data=record)


@router.get(
    "/case-studies/{case_study_id}",
    response_model=CaseStudyEnvelope,
    operation_id="getAdminCaseStudy",
)
@router.get(
    "/cases/{case_study_id}",
    response_model=CaseStudyEnvelope,
    operation_id="getAdminCase",
)
async def get_case_study(
    case_study_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> CaseStudyEnvelope:
    _require_permission(principal, "catalog.read")
    record = await _catalog_store(request).get_case_study(
        scope=_catalog_scope(principal),
        case_study_id=case_study_id,
    )
    _set_etag(response, record.version)
    return CaseStudyEnvelope(data=record)


@router.put(
    "/case-studies/{case_study_id}",
    response_model=CaseStudyEnvelope,
    operation_id="updateAdminCaseStudy",
)
@router.patch(
    "/case-studies/{case_study_id}",
    response_model=CaseStudyEnvelope,
    operation_id="patchAdminCaseStudy",
)
@router.patch(
    "/cases/{case_study_id}",
    response_model=CaseStudyEnvelope,
    operation_id="patchAdminCase",
)
async def update_case_study(
    case_study_id: uuid.UUID,
    body: UpdateCaseStudyRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> CaseStudyEnvelope:
    _require_permission(principal, "catalog.write")
    record = await _catalog_store(request).update_case_study(
        scope=_catalog_scope(principal),
        case_study_id=case_study_id,
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return CaseStudyEnvelope(data=record)


@router.post(
    "/case-studies/{case_study_id}/publish",
    response_model=CaseStudyEnvelope,
    operation_id="publishAdminCaseStudy",
)
@router.post(
    "/case-studies/{case_study_id}:publish",
    response_model=CaseStudyEnvelope,
    operation_id="publishAdminCaseStudyContractAlias",
)
@router.post(
    "/cases/{case_study_id}:publish",
    response_model=CaseStudyEnvelope,
    operation_id="publishAdminCase",
)
async def publish_case_study(
    case_study_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> CaseStudyEnvelope:
    _require_permission(principal, "catalog.publish")
    expected_version = parse_if_match(if_match)
    catalog_scope = _catalog_scope(principal)
    catalog = _catalog_store(request)
    draft = await catalog.get_case_study(
        scope=catalog_scope,
        case_study_id=case_study_id,
    )
    require_version(draft.version, expected_version)
    await _catalog_knowledge(request).sync_case_study(
        scope=_scope(principal),
        case_study=draft,
        trace_id=request_id_ctx.get(),
    )
    record = await catalog.publish_case_study(
        scope=catalog_scope,
        case_study_id=case_study_id,
        expected_version=expected_version,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return CaseStudyEnvelope(data=record)


@router.post(
    "/case-studies/{case_study_id}:schedule-publish",
    response_model=ScheduledPublishJobEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="scheduleAdminCaseStudyPublish",
)
@router.post(
    "/cases/{case_study_id}:schedule-publish",
    response_model=ScheduledPublishJobEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="scheduleAdminCasePublish",
)
async def schedule_case_study_publish(
    case_study_id: uuid.UUID,
    body: SchedulePublishRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ScheduledPublishJobEnvelope:
    _require_permission(principal, "catalog.publish")
    if body.version_id is not None:
        raise ApiError(422, "VERSION_ID_NOT_ALLOWED", "案例定时发布不能指定知识版本")
    expected_version = parse_if_match(if_match)
    scope = _catalog_scope(principal)
    draft = await _catalog_store(request).get_case_study(
        scope=scope, case_study_id=case_study_id
    )
    require_version(draft.version, expected_version)
    await _catalog_knowledge(request).sync_case_study(
        scope=_scope(principal), case_study=draft, trace_id=request_id_ctx.get()
    )
    job = await _scheduled_publish_store(request).schedule(
        scope=_scope(principal),
        resource_type=ScheduledPublishResourceType.CASE_STUDY,
        resource_id=case_study_id,
        expected_version=expected_version,
        scheduled_at=body.scheduled_at,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, job.version)
    return ScheduledPublishJobEnvelope(data=job)


@router.get(
    "/scheduled-publishes",
    response_model=ScheduledPublishJobListEnvelope,
    operation_id="listScheduledPublishes",
)
async def list_scheduled_publishes(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ScheduledPublishJobListEnvelope:
    _require_any_permission(principal, "catalog.read", "knowledge.read")
    records, total = await _scheduled_publish_store(request).list(
        scope=_scope(principal), limit=limit, offset=offset
    )
    return ScheduledPublishJobListEnvelope(
        data=records, total=total, limit=limit, offset=offset
    )


@router.get(
    "/scheduled-publishes/{job_id}",
    response_model=ScheduledPublishJobEnvelope,
    operation_id="getScheduledPublish",
)
async def get_scheduled_publish(
    job_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> ScheduledPublishJobEnvelope:
    _require_any_permission(principal, "catalog.read", "knowledge.read")
    job = await _scheduled_publish_store(request).get(scope=_scope(principal), job_id=job_id)
    _set_etag(response, job.version)
    return ScheduledPublishJobEnvelope(data=job)


@router.post(
    "/scheduled-publishes/{job_id}:cancel",
    response_model=ScheduledPublishJobEnvelope,
    operation_id="cancelScheduledPublish",
)
async def cancel_scheduled_publish(
    job_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ScheduledPublishJobEnvelope:
    _require_any_permission(principal, "catalog.publish", "knowledge.publish")
    job = await _scheduled_publish_store(request).cancel(
        scope=_scope(principal),
        job_id=job_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, job.version)
    return ScheduledPublishJobEnvelope(data=job)


@router.post(
    "/case-studies/{case_study_id}/archive",
    response_model=CaseStudyEnvelope,
    operation_id="archiveAdminCaseStudy",
)
async def archive_case_study(
    case_study_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> CaseStudyEnvelope:
    _require_permission(principal, "catalog.publish")
    record = await _catalog_store(request).archive_case_study(
        scope=_catalog_scope(principal),
        case_study_id=case_study_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return CaseStudyEnvelope(data=record)


@router.delete(
    "/case-studies/{case_study_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteAdminCaseStudy",
)
@router.delete(
    "/cases/{case_study_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteAdminCase",
)
async def delete_case_study(
    case_study_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> None:
    _require_permission(principal, "catalog.write")
    await _catalog_store(request).delete_case_study(
        scope=_catalog_scope(principal),
        case_study_id=case_study_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )


@router.get(
    "/forbidden-topics",
    response_model=ForbiddenTopicListEnvelope,
    operation_id="listAdminForbiddenTopics",
)
async def list_forbidden_topics(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    active: Annotated[bool | None, Query()] = None,
) -> ForbiddenTopicListEnvelope:
    _require_permission(principal, "forbidden_topic.read")
    records, total = await _catalog_store(request).list_forbidden_topics(
        scope=_catalog_scope(principal),
        limit=limit,
        offset=offset,
        active=active,
    )
    return ForbiddenTopicListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/forbidden-topics",
    response_model=ForbiddenTopicEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminForbiddenTopic",
)
async def create_forbidden_topic(
    body: CreateForbiddenTopicRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> ForbiddenTopicEnvelope:
    _require_permission(principal, "forbidden_topic.write")
    record = await _catalog_store(request).create_forbidden_topic(
        scope=_catalog_scope(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ForbiddenTopicEnvelope(data=record)


@router.get(
    "/forbidden-topics/{topic_id}",
    response_model=ForbiddenTopicEnvelope,
    operation_id="getAdminForbiddenTopic",
)
async def get_forbidden_topic(
    topic_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> ForbiddenTopicEnvelope:
    _require_permission(principal, "forbidden_topic.read")
    record = await _catalog_store(request).get_forbidden_topic(
        scope=_catalog_scope(principal),
        topic_id=topic_id,
    )
    _set_etag(response, record.version)
    return ForbiddenTopicEnvelope(data=record)


@router.put(
    "/forbidden-topics/{topic_id}",
    response_model=ForbiddenTopicEnvelope,
    operation_id="updateAdminForbiddenTopic",
)
@router.patch(
    "/forbidden-topics/{topic_id}",
    response_model=ForbiddenTopicEnvelope,
    operation_id="patchAdminForbiddenTopic",
)
async def update_forbidden_topic(
    topic_id: uuid.UUID,
    body: UpdateForbiddenTopicRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ForbiddenTopicEnvelope:
    _require_permission(principal, "forbidden_topic.write")
    record = await _catalog_store(request).update_forbidden_topic(
        scope=_catalog_scope(principal),
        topic_id=topic_id,
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ForbiddenTopicEnvelope(data=record)


@router.post(
    "/forbidden-topics/{topic_id}/activate",
    response_model=ForbiddenTopicEnvelope,
    operation_id="activateAdminForbiddenTopic",
)
async def activate_forbidden_topic(
    topic_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ForbiddenTopicEnvelope:
    _require_permission(principal, "forbidden_topic.write")
    record = await _catalog_store(request).set_forbidden_topic_active(
        scope=_catalog_scope(principal),
        topic_id=topic_id,
        expected_version=parse_if_match(if_match),
        active=True,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ForbiddenTopicEnvelope(data=record)


@router.post(
    "/forbidden-topics/{topic_id}/deactivate",
    response_model=ForbiddenTopicEnvelope,
    operation_id="deactivateAdminForbiddenTopic",
)
async def deactivate_forbidden_topic(
    topic_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ForbiddenTopicEnvelope:
    _require_permission(principal, "forbidden_topic.write")
    record = await _catalog_store(request).set_forbidden_topic_active(
        scope=_catalog_scope(principal),
        topic_id=topic_id,
        expected_version=parse_if_match(if_match),
        active=False,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ForbiddenTopicEnvelope(data=record)


@router.delete(
    "/forbidden-topics/{topic_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteAdminForbiddenTopic",
)
async def delete_forbidden_topic(
    topic_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> None:
    _require_permission(principal, "forbidden_topic.write")
    await _catalog_store(request).delete_forbidden_topic(
        scope=_catalog_scope(principal),
        topic_id=topic_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )


@router.get(
    "/cards",
    response_model=ManagedCardListEnvelope,
    operation_id="listAdminCards",
)
async def list_cards(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    content_status: Annotated[ContentStatus | None, Query(alias="status")] = None,
    card_kind: Annotated[CardKind | None, Query(alias="card_kind")] = None,
) -> ManagedCardListEnvelope:
    _require_permission(principal, "card.read")
    records, total = await _catalog_store(request).list_cards(
        scope=_catalog_scope(principal),
        limit=limit,
        offset=offset,
        status=content_status,
        card_kind=card_kind,
    )
    return ManagedCardListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.post(
    "/cards",
    response_model=ManagedCardEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createAdminCard",
)
async def create_card(
    body: CreateCardRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> ManagedCardEnvelope:
    _require_permission(principal, "card.write")
    record = await _catalog_store(request).create_card(
        scope=_catalog_scope(principal),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ManagedCardEnvelope(data=record)


@router.get(
    "/cards/{card_id}",
    response_model=ManagedCardEnvelope,
    operation_id="getManagedAdminCard",
)
async def get_managed_card(
    card_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
) -> ManagedCardEnvelope:
    _require_permission(principal, "card.read")
    record = await _catalog_store(request).get_card(
        scope=_catalog_scope(principal),
        card_id=card_id,
    )
    _set_etag(response, record.version)
    return ManagedCardEnvelope(data=record)


@router.get(
    "/cards/{card_id}/wecom-contact-way",
    response_model=WeComCardContactWayEnvelope,
    operation_id="getAdminCardWeComContactWay",
)
async def get_card_wecom_contact_way(
    card_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> WeComCardContactWayEnvelope:
    _require_permission(principal, "card.read")
    scope = _catalog_scope(principal)
    record = await _wecom_store(request).get_card_contact_way(
        tenant_id=scope.tenant_id,
        company_id=scope.company_id,
        actor_user_id=scope.actor_user_id,
        card_id=card_id,
        card_owner_only=scope.is_card_owner,
    )
    return WeComCardContactWayEnvelope(
        data=_wecom_contact_record(record) if record is not None else None
    )


@router.post(
    "/cards/{card_id}/wecom-contact-way",
    response_model=WeComCardContactWayEnvelope,
    operation_id="provisionAdminCardWeComContactWay",
)
async def provision_card_wecom_contact_way(
    card_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> WeComCardContactWayEnvelope:
    _require_permission(principal, "card.write")
    scope = _catalog_scope(principal)
    store = _wecom_store(request)
    provisioning = await store.prepare_card_contact_way(
        tenant_id=scope.tenant_id,
        company_id=scope.company_id,
        actor_user_id=scope.actor_user_id,
        card_id=card_id,
        card_owner_only=scope.is_card_owner,
    )
    if provisioning.existing is not None:
        return WeComCardContactWayEnvelope(
            data=_wecom_contact_record(provisioning.existing)
        )
    try:
        provider_contact = await _wecom_client(request).add_contact_way(
            user_ids=(provisioning.wecom_user_id,),
            state=provisioning.state,
            remark=f"数智名片-{provisioning.card_display_name}",
        )
    except WeComConfigurationError as exc:
        raise ApiError(409, "WECOM_NOT_CONFIGURED", "企业微信尚未完成配置") from exc
    except WeComProviderError as exc:
        raise ApiError(
            502,
            exc.code,
            "企业微信暂时无法生成联系入口，请核对客户联系权限",
            details={"provider_code": exc.provider_code} if exc.provider_code else None,
        ) from exc
    record = await store.save_card_contact_way(
        tenant_id=scope.tenant_id,
        company_id=scope.company_id,
        actor_user_id=scope.actor_user_id,
        provisioning=provisioning,
        config_id=provider_contact.config_id,
        qr_code_url=provider_contact.qr_code_url,
        trace_id=request_id_ctx.get(),
    )
    return WeComCardContactWayEnvelope(data=_wecom_contact_record(record))


@router.put(
    "/cards/{card_id}",
    response_model=ManagedCardEnvelope,
    operation_id="updateManagedAdminCard",
)
@router.patch(
    "/cards/{card_id}",
    response_model=ManagedCardEnvelope,
    operation_id="patchManagedAdminCard",
)
async def update_managed_card(
    card_id: uuid.UUID,
    body: UpdateManagedCardRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ManagedCardEnvelope:
    _require_permission(principal, "card.write")
    record = await _catalog_store(request).update_card(
        scope=_catalog_scope(principal),
        card_id=card_id,
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ManagedCardEnvelope(data=record)


@router.get(
    "/cards/{card_id}/enterprise-template",
    response_model=EnterpriseTemplateEnvelope,
    operation_id="getAdminEnterpriseCardTemplate",
)
async def get_enterprise_card_template(
    card_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> EnterpriseTemplateEnvelope:
    _require_permission(principal, "card.read")
    record = await _catalog_store(request).get_enterprise_template(
        scope=_catalog_scope(principal), card_id=card_id
    )
    return EnterpriseTemplateEnvelope(data=record)


@router.put(
    "/cards/{card_id}/enterprise-template",
    response_model=EnterpriseTemplateEnvelope,
    operation_id="updateAdminEnterpriseCardTemplate",
)
async def update_enterprise_card_template(
    card_id: uuid.UUID,
    body: UpdateEnterpriseTemplateRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> EnterpriseTemplateEnvelope:
    _require_permission(principal, "card.write")
    record = await _catalog_store(request).update_enterprise_template(
        scope=_catalog_scope(principal),
        card_id=card_id,
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return EnterpriseTemplateEnvelope(data=record)


@router.get(
    "/card-composer/defaults/{card_kind}",
    response_model=CardComposerDefaultEnvelope,
    operation_id="getAdminCardComposerDefault",
)
async def get_card_composer_default(
    card_kind: str,
    request: Request,
    principal: StaffDependency,
) -> CardComposerDefaultEnvelope:
    _require_permission(principal, "card.read")
    record = await _catalog_store(request).get_card_composer_default(
        scope=_catalog_scope(principal), card_kind=card_kind
    )
    return CardComposerDefaultEnvelope(data=record)


@router.put(
    "/card-composer/defaults/{card_kind}",
    response_model=CardComposerDefaultEnvelope,
    operation_id="updateAdminCardComposerDefault",
)
async def update_card_composer_default(
    card_kind: str,
    body: UpdateCardComposerDefaultRequest,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> CardComposerDefaultEnvelope:
    _require_permission(principal, "card.write")
    record = await _catalog_store(request).update_card_composer_default(
        scope=_catalog_scope(principal),
        card_kind=card_kind,
        expected_version=parse_if_match(if_match),
        body=body,
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return CardComposerDefaultEnvelope(data=record)


@router.post(
    "/cards/{card_id}/publish",
    response_model=ManagedCardEnvelope,
    operation_id="publishManagedAdminCard",
)
@router.post(
    "/cards/{card_id}:publish",
    response_model=ManagedCardEnvelope,
    operation_id="publishManagedAdminCardContractAlias",
)
async def publish_managed_card(
    card_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ManagedCardEnvelope:
    _require_permission(principal, "card.write")
    record = await _catalog_store(request).publish_card(
        scope=_catalog_scope(principal),
        card_id=card_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ManagedCardEnvelope(data=record)


@router.post(
    "/cards/{card_id}/deactivate",
    response_model=ManagedCardEnvelope,
    operation_id="deactivateManagedAdminCard",
)
@router.post(
    "/cards/{card_id}:deactivate",
    response_model=ManagedCardEnvelope,
    operation_id="deactivateManagedAdminCardContractAlias",
)
async def deactivate_managed_card(
    card_id: uuid.UUID,
    request: Request,
    response: Response,
    principal: StaffDependency,
    if_match: IfMatchDependency,
) -> ManagedCardEnvelope:
    _require_permission(principal, "card.write")
    record = await _catalog_store(request).deactivate_card(
        scope=_catalog_scope(principal),
        card_id=card_id,
        expected_version=parse_if_match(if_match),
        trace_id=request_id_ctx.get(),
    )
    _set_etag(response, record.version)
    return ManagedCardEnvelope(data=record)


__all__ = ["parse_if_match", "router"]
