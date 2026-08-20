from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.workflow_schemas import (
    CreateLeadFollowupRequest,
    LeadCaptureRequest,
    LeadCreated,
    LeadDetail,
    LeadFollowupView,
    LeadListItem,
    PrivacyRequestCreate,
    PrivacyRequestView,
    UpdateLeadRequest,
    UpdatePrivacyRequest,
)
from app.commercial.entitlements import feature_is_enabled
from app.core.config import Settings
from app.core.pii import PiiCipher, mask_value
from app.core.tokens import VisitorPrincipal
from app.db.models import (
    Card,
    Company,
    ConsentRecord,
    ConsentScope,
    ContentStatus,
    Conversation,
    Lead,
    LeadFollowup,
    LeadStatus,
    Message,
    Notification,
    OutboxEvent,
    OutboxStatus,
    PrivacyRequest,
    PrivacyRequestStatus,
    PrivacyRequestType,
    Visit,
    Visitor,
    VisitorProfile,
    VisitorProfileSignal,
    VisitSummary,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit
from app.services.public_store import PublicStore, canonical_request_hash


@dataclass(frozen=True, slots=True)
class CrmScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    role: str

    @property
    def is_card_owner(self) -> bool:
        return self.role == "card_owner"


class CrmStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._cipher = PiiCipher.from_settings(settings)

    async def create_public_lead(
        self,
        *,
        slug: str,
        principal: VisitorPrincipal,
        body: LeadCaptureRequest,
        idempotency_key: str,
    ) -> LeadCreated:
        async with self._sessions() as session, session.begin():
            await self._set_visitor_scope(session, principal, card_slug=slug)
            card = await self._principal_card(session, principal=principal, slug=slug)
            company = await session.get(Company, principal.company_id)
            if company is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "企业不存在")
            if not feature_is_enabled(company.settings, "customer.leads"):
                raise ApiError(
                    403,
                    "FEATURE_NOT_ENTITLED",
                    "当前企业套餐未开通销售线索",
                    details={"feature_id": "customer.leads"},
                )
            expected_policy = _policy_version(card, ConsentScope.LEAD_CONTACT)
            if body.consent_policy_version != expected_policy:
                raise ApiError(
                    409,
                    "POLICY_VERSION_MISMATCH",
                    "留资授权告知已更新，请刷新页面后重新确认",
                )
            consent = await self._latest_consent(
                session,
                principal=principal,
                scope=ConsentScope.LEAD_CONTACT,
                policy_version=expected_policy,
            )
            if (
                consent is None
                or not consent.granted
                or (consent.expires_at is not None and consent.expires_at <= datetime.now(UTC))
            ):
                raise ApiError(403, "CONSENT_REQUIRED", "请先确认有效的留资授权")
            if body.conversation_id is not None:
                conversation = await session.scalar(
                    select(Conversation).where(
                        Conversation.id == body.conversation_id,
                        Conversation.tenant_id == principal.tenant_id,
                        Conversation.company_id == principal.company_id,
                        Conversation.card_id == principal.card_id,
                        Conversation.visitor_id == principal.visitor_id,
                    )
                )
                if conversation is None:
                    raise ApiError(404, "RESOURCE_NOT_FOUND", "对话不存在或不属于当前访客")
            claim = await PublicStore._claim_idempotency(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                scope=f"public.lead:{principal.visitor_id}",
                key=idempotency_key,
                request_hash=canonical_request_hash("create_lead", body.model_dump(mode="json")),
            )
            if claim.replay:
                if claim.record.resource_id is None:
                    raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "请求仍在处理中")
                lead = await session.get(Lead, claim.record.resource_id)
                if lead is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等记录已失效")
                return LeadCreated(id=lead.id, status=lead.status.value, created_at=lead.created_at)

            profile = await session.scalar(
                select(VisitorProfile)
                .where(
                    VisitorProfile.tenant_id == principal.tenant_id,
                    VisitorProfile.company_id == principal.company_id,
                    VisitorProfile.visitor_id == principal.visitor_id,
                )
                .with_for_update()
            )
            if profile is None:
                profile = VisitorProfile(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    visitor_id=principal.visitor_id,
                    encryption_key_ref=self._cipher.key_ref,
                )
                session.add(profile)
            profile.name_ciphertext = self._cipher.encrypt(body.name)
            profile.mobile_ciphertext = self._encrypt_optional(body.mobile)
            profile.mobile_hmac = self._hmac_optional(body.mobile)
            profile.email_ciphertext = self._encrypt_optional(body.email)
            profile.email_hmac = self._hmac_optional(body.email)
            profile.wechat_ciphertext = self._encrypt_optional(body.wechat)
            profile.company_name = body.company_name
            profile.demand_ciphertext = self._cipher.encrypt(body.demand)
            profile.encryption_key_ref = self._cipher.key_ref

            lead = Lead(
                id=uuid.uuid4(),
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                card_id=principal.card_id,
                visitor_id=principal.visitor_id,
                conversation_id=body.conversation_id,
                owner_user_id=card.responsible_user_id,
                status=LeadStatus.NEW,
                priority="medium",
                requirement_ciphertext=self._cipher.encrypt(body.demand),
                encryption_key_ref=self._cipher.key_ref,
                interest_tags=body.interest_tags,
            )
            session.add(lead)
            session.add(
                Notification(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    recipient_user_id=card.responsible_user_id,
                    notification_type="lead_created",
                    title="收到新线索",
                    body="访客已主动留下联系方式和需求，请及时跟进。",
                    resource_type="lead",
                    resource_id=lead.id,
                )
            )
            session.add(
                OutboxEvent(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    aggregate_type="lead",
                    aggregate_id=lead.id,
                    aggregate_version=1,
                    event_type="lead.created.v1",
                    payload={
                        "lead_id": str(lead.id),
                        "card_id": str(lead.card_id),
                        "owner_user_id": str(lead.owner_user_id),
                    },
                    headers={"contains_pii": False},
                    deduplication_key=f"lead.created:{lead.id}",
                    status=OutboxStatus.PENDING,
                )
            )
            await session.flush()
            PublicStore._complete_idempotency(
                claim.record,
                resource_type="lead",
                resource_id=lead.id,
                status_code=201,
                response_body={"lead_id": str(lead.id)},
            )
            return LeadCreated(id=lead.id, status=lead.status.value, created_at=lead.created_at)

    async def create_privacy_request(
        self,
        *,
        principal: VisitorPrincipal,
        body: PrivacyRequestCreate,
        idempotency_key: str,
    ) -> PrivacyRequestView:
        async with self._sessions() as session, session.begin():
            await self._set_visitor_scope(session, principal)
            card = await self._principal_card(session, principal=principal)
            visitor = await session.scalar(
                select(Visitor).where(
                    Visitor.id == principal.visitor_id,
                    Visitor.tenant_id == principal.tenant_id,
                    Visitor.company_id == principal.company_id,
                )
            )
            if visitor is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "访客会话不存在")
            claim = await PublicStore._claim_idempotency(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                scope=f"public.privacy:{principal.visitor_id}",
                key=idempotency_key,
                request_hash=canonical_request_hash(
                    "create_privacy_request", body.model_dump(mode="json")
                ),
            )
            if claim.replay:
                if claim.record.resource_id is None:
                    raise ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "请求仍在处理中")
                existing = await session.get(PrivacyRequest, claim.record.resource_id)
                if existing is None:
                    raise ApiError(409, "IDEMPOTENCY_CONFLICT", "幂等记录已失效")
                return self._privacy_view(existing)

            privacy_request = PrivacyRequest(
                id=uuid.uuid4(),
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
                visitor_id=principal.visitor_id,
                request_type=PrivacyRequestType(body.request_type),
                status=PrivacyRequestStatus.PENDING,
                note_ciphertext=self._encrypt_optional(body.note),
                encryption_key_ref=self._cipher.key_ref,
                evidence={
                    "card_id": str(principal.card_id),
                    "visit_id": str(principal.visit_id),
                    **({"consent_scope": body.consent_scope} if body.consent_scope else {}),
                },
            )
            session.add(privacy_request)
            if body.request_type == "withdraw_consent" and body.consent_scope:
                scope = ConsentScope(body.consent_scope)
                if scope == ConsentScope.PROFILE_PERSONALIZATION:
                    await self._lock_visitor(session, principal.visitor_id)
                    company = await session.get(Company, principal.company_id)
                    company_settings = (
                        company.settings
                        if company is not None and isinstance(company.settings, dict)
                        else {}
                    )
                    policies = company_settings.get("policy_versions", {})
                    if not isinstance(policies, dict):
                        policies = {}
                    policy_version = str(
                        policies.get("profile_personalization")
                        or "profile-personalization-v1"
                    )
                else:
                    policy_version = _policy_version(card, scope)
                session.add(
                    ConsentRecord(
                        id=uuid.uuid4(),
                        tenant_id=principal.tenant_id,
                        company_id=principal.company_id,
                        visitor_id=principal.visitor_id,
                        scope=scope,
                        policy_version=policy_version,
                        granted=False,
                        evidence={
                            "card_id": str(principal.card_id),
                            "visit_id": str(principal.visit_id),
                            "privacy_request_id": str(privacy_request.id),
                        },
                    )
                )
                if scope == ConsentScope.PROFILE_PERSONALIZATION:
                    await session.execute(
                        delete(VisitorProfileSignal).where(
                            VisitorProfileSignal.tenant_id == principal.tenant_id,
                            VisitorProfileSignal.company_id == principal.company_id,
                            VisitorProfileSignal.visitor_id == principal.visitor_id,
                        )
                    )
            session.add(
                Notification(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    recipient_user_id=card.responsible_user_id,
                    notification_type="privacy_request_created",
                    title="收到隐私权利请求",
                    body="访客提交了数据权利请求，请按合规流程及时处理。",
                    resource_type="privacy_request",
                    resource_id=privacy_request.id,
                )
            )
            session.add(
                OutboxEvent(
                    id=uuid.uuid4(),
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    aggregate_type="privacy_request",
                    aggregate_id=privacy_request.id,
                    aggregate_version=1,
                    event_type="privacy_request.created.v1",
                    payload={
                        "privacy_request_id": str(privacy_request.id),
                        "request_type": privacy_request.request_type.value,
                    },
                    headers={"contains_pii": False},
                    deduplication_key=f"privacy.created:{privacy_request.id}",
                    status=OutboxStatus.PENDING,
                )
            )
            await session.flush()
            PublicStore._complete_idempotency(
                claim.record,
                resource_type="privacy_request",
                resource_id=privacy_request.id,
                status_code=201,
                response_body={"privacy_request_id": str(privacy_request.id)},
            )
            return self._privacy_view(privacy_request)

    async def get_public_privacy_request(
        self,
        *,
        principal: VisitorPrincipal,
        request_id: uuid.UUID,
    ) -> PrivacyRequestView:
        async with self._sessions() as session, session.begin():
            await self._set_visitor_scope(session, principal)
            record = await session.scalar(
                select(PrivacyRequest).where(
                    PrivacyRequest.id == request_id,
                    PrivacyRequest.tenant_id == principal.tenant_id,
                    PrivacyRequest.company_id == principal.company_id,
                    PrivacyRequest.visitor_id == principal.visitor_id,
                )
            )
            if record is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "隐私请求不存在")
            return self._privacy_view(record)

    async def list_leads(
        self,
        *,
        scope: CrmScope,
        limit: int,
        offset: int,
        status: str | None,
    ) -> tuple[list[LeadListItem], int]:
        async with self._sessions() as session, session.begin():
            await self._set_staff_scope(session, scope)
            filters = [
                Lead.tenant_id == scope.tenant_id,
                Lead.company_id == scope.company_id,
                *self._card_filters(scope),
            ]
            if status:
                filters.append(Lead.status == status)
            total = int(
                await session.scalar(
                    select(func.count(Lead.id))
                    .select_from(Lead)
                    .join(Card, Card.id == Lead.card_id)
                    .where(*filters)
                )
                or 0
            )
            rows = (
                await session.execute(
                    select(Lead, Card.display_name, VisitorProfile)
                    .join(Card, Card.id == Lead.card_id)
                    .outerjoin(VisitorProfile, VisitorProfile.visitor_id == Lead.visitor_id)
                    .where(*filters)
                    .order_by(Lead.created_at.desc(), Lead.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [
                self._lead_list_item(lead, name, profile) for lead, name, profile in rows
            ], total

    async def get_lead(
        self,
        *,
        scope: CrmScope,
        lead_id: uuid.UUID,
        trace_id: str | None,
    ) -> LeadDetail:
        async with self._sessions() as session, session.begin():
            await self._set_staff_scope(session, scope)
            lead, card = await self._lead(session, scope=scope, lead_id=lead_id, for_update=True)
            profile = await session.scalar(
                select(VisitorProfile).where(VisitorProfile.visitor_id == lead.visitor_id)
            )
            if profile is None or profile.name_ciphertext is None:
                raise ApiError(409, "LEAD_PROFILE_UNAVAILABLE", "线索资料已删除或不可用")
            if lead.status == LeadStatus.NEW:
                lead.status = LeadStatus.VIEWED
                lead.viewed_at = datetime.now(UTC)
                lead.version += 1
            followups = (
                await session.scalars(
                    select(LeadFollowup)
                    .where(LeadFollowup.lead_id == lead.id)
                    .order_by(LeadFollowup.created_at, LeadFollowup.id)
                )
            ).all()
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="lead.pii_read",
                resource_type="lead",
                resource_id=lead.id,
                trace_id=trace_id,
                event_data={"visitor_id": lead.visitor_id},
            )
            await session.flush()
            await session.refresh(lead)
            base = self._lead_list_item(lead, card.display_name, profile)
            return LeadDetail(
                **base.model_dump(),
                name=self._cipher.decrypt(profile.name_ciphertext),
                mobile=self._decrypt_optional(profile.mobile_ciphertext),
                email=self._decrypt_optional(profile.email_ciphertext),
                wechat=self._decrypt_optional(profile.wechat_ciphertext),
                demand=self._cipher.decrypt(lead.requirement_ciphertext),
                followups=[self._followup_view(item) for item in followups],
            )

    async def update_lead(
        self,
        *,
        scope: CrmScope,
        lead_id: uuid.UUID,
        expected_version: int,
        body: UpdateLeadRequest,
        trace_id: str | None,
    ) -> LeadDetail:
        async with self._sessions() as session, session.begin():
            await self._set_staff_scope(session, scope)
            lead, card = await self._lead(session, scope=scope, lead_id=lead_id, for_update=True)
            if lead.version != expected_version:
                raise ApiError(
                    409,
                    "VERSION_CONFLICT",
                    "线索已被其他操作更新，请刷新后重试",
                    details={"current_version": lead.version},
                )
            previous_status = lead.status
            lead.status = LeadStatus(body.status)
            lead.priority = body.priority
            if lead.status in {LeadStatus.WON, LeadStatus.LOST, LeadStatus.INVALID}:
                lead.closed_at = datetime.now(UTC)
            else:
                lead.closed_at = None
            if lead.status != LeadStatus.NEW and lead.viewed_at is None:
                lead.viewed_at = datetime.now(UTC)
            lead.version += 1
            if previous_status != lead.status:
                session.add(
                    LeadFollowup(
                        id=uuid.uuid4(),
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                        lead_id=lead.id,
                        actor_user_id=scope.actor_user_id,
                        followup_type="status_change",
                        content_ciphertext=self._cipher.encrypt(
                            f"状态从 {previous_status.value} 变更为 {lead.status.value}"
                        ),
                        encryption_key_ref=self._cipher.key_ref,
                    )
                )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="lead.update",
                resource_type="lead",
                resource_id=lead.id,
                trace_id=trace_id,
                event_data={
                    "from_status": previous_status.value,
                    "to_status": lead.status.value,
                    "priority": lead.priority,
                },
            )
            await session.flush()
        return await self.get_lead(scope=scope, lead_id=lead_id, trace_id=trace_id)

    async def add_followup(
        self,
        *,
        scope: CrmScope,
        lead_id: uuid.UUID,
        body: CreateLeadFollowupRequest,
        trace_id: str | None,
    ) -> LeadFollowupView:
        async with self._sessions() as session, session.begin():
            await self._set_staff_scope(session, scope)
            lead, _ = await self._lead(session, scope=scope, lead_id=lead_id, for_update=True)
            followup = LeadFollowup(
                id=uuid.uuid4(),
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                lead_id=lead.id,
                actor_user_id=scope.actor_user_id,
                followup_type=body.followup_type,
                content_ciphertext=self._cipher.encrypt(body.content),
                encryption_key_ref=self._cipher.key_ref,
                next_at=body.next_at,
            )
            session.add(followup)
            if lead.status in {LeadStatus.NEW, LeadStatus.VIEWED}:
                lead.status = LeadStatus.FOLLOWING
                lead.viewed_at = lead.viewed_at or datetime.now(UTC)
                lead.version += 1
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="lead.followup.append",
                resource_type="lead_followup",
                resource_id=followup.id,
                trace_id=trace_id,
                event_data={"lead_id": lead.id, "followup_type": followup.followup_type},
            )
            await session.flush()
            await session.refresh(followup)
            return self._followup_view(followup)

    async def list_privacy_requests(
        self,
        *,
        scope: CrmScope,
        limit: int,
        offset: int,
        status: str | None,
    ) -> tuple[list[PrivacyRequestView], int]:
        async with self._sessions() as session, session.begin():
            await self._set_staff_scope(session, scope)
            filters = [
                PrivacyRequest.tenant_id == scope.tenant_id,
                PrivacyRequest.company_id == scope.company_id,
            ]
            if status:
                filters.append(PrivacyRequest.status == status)
            total = int(
                await session.scalar(select(func.count(PrivacyRequest.id)).where(*filters)) or 0
            )
            rows = (
                await session.scalars(
                    select(PrivacyRequest)
                    .where(*filters)
                    .order_by(PrivacyRequest.created_at.desc(), PrivacyRequest.id.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [self._privacy_view(item) for item in rows], total

    async def update_privacy_request(
        self,
        *,
        scope: CrmScope,
        request_id: uuid.UUID,
        body: UpdatePrivacyRequest,
        trace_id: str | None,
    ) -> PrivacyRequestView:
        async with self._sessions() as session, session.begin():
            await self._set_staff_scope(session, scope)
            record = await session.scalar(
                select(PrivacyRequest)
                .where(
                    PrivacyRequest.id == request_id,
                    PrivacyRequest.tenant_id == scope.tenant_id,
                    PrivacyRequest.company_id == scope.company_id,
                )
                .with_for_update()
            )
            if record is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "隐私请求不存在")
            target = PrivacyRequestStatus(body.status)
            if record.status in {PrivacyRequestStatus.COMPLETED, PrivacyRequestStatus.REJECTED}:
                if record.status != target:
                    raise ApiError(409, "PRIVACY_REQUEST_FINAL", "隐私请求已处于终态")
            if target in {
                PrivacyRequestStatus.VERIFIED,
                PrivacyRequestStatus.IN_PROGRESS,
                PrivacyRequestStatus.COMPLETED,
            } and not (body.verification_method or record.verification_method):
                raise ApiError(409, "VERIFICATION_REQUIRED", "处理前必须记录身份核验方式")
            record.status = target
            record.verification_method = body.verification_method or record.verification_method
            record.handled_by = scope.actor_user_id
            if target == PrivacyRequestStatus.COMPLETED:
                record.completed_at = datetime.now(UTC)
                if record.request_type == PrivacyRequestType.DELETION:
                    await self._delete_visitor_personal_data(
                        session,
                        tenant_id=scope.tenant_id,
                        company_id=scope.company_id,
                        visitor_id=record.visitor_id,
                    )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="privacy_request.update",
                resource_type="privacy_request",
                resource_id=record.id,
                trace_id=trace_id,
                event_data={"status": target.value, "request_type": record.request_type.value},
            )
            await session.flush()
            await session.refresh(record)
            return self._privacy_view(record)

    async def _delete_visitor_personal_data(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        visitor_id: uuid.UUID,
    ) -> None:
        await self._lock_visitor(session, visitor_id)
        session.add(
            ConsentRecord(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                company_id=company_id,
                visitor_id=visitor_id,
                scope=ConsentScope.PROFILE_PERSONALIZATION,
                policy_version="erasure-tombstone-v1",
                granted=False,
                evidence={"reason": "verified_deletion_request"},
            )
        )
        await session.execute(
            delete(VisitorProfileSignal).where(
                VisitorProfileSignal.tenant_id == tenant_id,
                VisitorProfileSignal.company_id == company_id,
                VisitorProfileSignal.visitor_id == visitor_id,
            )
        )
        summaries = (
            await session.scalars(
                select(VisitSummary)
                .join(Conversation, Conversation.id == VisitSummary.conversation_id)
                .where(
                    VisitSummary.tenant_id == tenant_id,
                    VisitSummary.company_id == company_id,
                    Conversation.visitor_id == visitor_id,
                )
            )
        ).all()
        for summary in summaries:
            summary.summary = "[已根据访客隐私请求删除]"
            summary.interests = []
            summary.strength = None
            summary.next_step = None
            summary.risk_notes = None
            summary.source_message_ids = []
            summary.approved_at = None
            summary.approved_by = None
        conversations = (
            await session.scalars(
                select(Conversation).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.company_id == company_id,
                    Conversation.visitor_id == visitor_id,
                )
            )
        ).all()
        for conversation in conversations:
            conversation.primary_intent = None
        visits = (
            await session.scalars(
                select(Visit).where(
                    Visit.tenant_id == tenant_id,
                    Visit.company_id == company_id,
                    Visit.visitor_id == visitor_id,
                )
            )
        ).all()
        for visit in visits:
            context = visit.context if isinstance(visit.context, dict) else {}
            visit.context = {
                key: context[key]
                for key in ("privacy_notice_version",)
                if key in context
            }
        profile = await session.scalar(
            select(VisitorProfile)
            .where(
                VisitorProfile.tenant_id == tenant_id,
                VisitorProfile.company_id == company_id,
                VisitorProfile.visitor_id == visitor_id,
            )
            .with_for_update()
        )
        if profile is not None:
            profile.name_ciphertext = None
            profile.mobile_ciphertext = None
            profile.mobile_hmac = None
            profile.email_ciphertext = None
            profile.email_hmac = None
            profile.wechat_ciphertext = None
            profile.company_name = None
            profile.demand_ciphertext = None
        redacted = "[已根据访客隐私请求删除]"
        await session.execute(
            update(Message)
            .where(
                Message.tenant_id == tenant_id,
                Message.company_id == company_id,
                Message.conversation_id.in_(
                    select(Conversation.id).where(Conversation.visitor_id == visitor_id)
                ),
            )
            .values(content=redacted, content_redacted=True)
        )
        leads = (
            await session.scalars(
                select(Lead).where(
                    Lead.tenant_id == tenant_id,
                    Lead.company_id == company_id,
                    Lead.visitor_id == visitor_id,
                )
            )
        ).all()
        for lead in leads:
            lead.requirement_ciphertext = self._cipher.encrypt(redacted)
        # Runtime users have no UPDATE privilege on append-only follow-ups.  A
        # narrowly scoped SECURITY DEFINER function replaces only this visitor's
        # ciphertext with an undecryptable tombstone for a verified erasure.
        await session.execute(
            text(
                "SELECT app.erase_visitor_lead_followups("
                ":tenant_id, :company_id, :visitor_id)"
            ),
            {
                "tenant_id": tenant_id,
                "company_id": company_id,
                "visitor_id": visitor_id,
            },
        )
        visitor = await session.scalar(
            select(Visitor).where(
                Visitor.id == visitor_id,
                Visitor.tenant_id == tenant_id,
                Visitor.company_id == company_id,
            )
        )
        if visitor is not None:
            visitor.anonymous_hash = self._cipher.hmac(f"deleted:{uuid.uuid4()}")

    @staticmethod
    async def _lock_visitor(session: AsyncSession, visitor_id: uuid.UUID) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:visitor_id, 0))"),
            {"visitor_id": str(visitor_id)},
        )

    async def _lead(
        self,
        session: AsyncSession,
        *,
        scope: CrmScope,
        lead_id: uuid.UUID,
        for_update: bool,
    ) -> tuple[Lead, Card]:
        statement = (
            select(Lead, Card)
            .join(Card, Card.id == Lead.card_id)
            .where(
                Lead.id == lead_id,
                Lead.tenant_id == scope.tenant_id,
                Lead.company_id == scope.company_id,
                *self._card_filters(scope),
            )
        )
        if for_update:
            statement = statement.with_for_update(of=Lead)
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "线索不存在或不在当前作用域")
        return row

    async def _principal_card(
        self,
        session: AsyncSession,
        *,
        principal: VisitorPrincipal,
        slug: str | None = None,
    ) -> Card:
        filters = [
            Card.id == principal.card_id,
            Card.tenant_id == principal.tenant_id,
            Card.company_id == principal.company_id,
            Card.status == ContentStatus.PUBLISHED,
            Card.deleted_at.is_(None),
        ]
        if slug is not None:
            filters.append(Card.slug == slug)
        card = await session.scalar(select(Card).where(*filters))
        if card is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "名片不存在")
        return card

    async def _latest_consent(
        self,
        session: AsyncSession,
        *,
        principal: VisitorPrincipal,
        scope: ConsentScope,
        policy_version: str,
    ) -> ConsentRecord | None:
        return await session.scalar(
            select(ConsentRecord)
            .where(
                ConsentRecord.tenant_id == principal.tenant_id,
                ConsentRecord.company_id == principal.company_id,
                ConsentRecord.visitor_id == principal.visitor_id,
                ConsentRecord.scope == scope,
                ConsentRecord.policy_version == policy_version,
                ConsentRecord.evidence["card_id"].astext == str(principal.card_id),
            )
            .order_by(ConsentRecord.recorded_at.desc(), ConsentRecord.id.desc())
            .limit(1)
        )

    async def _set_visitor_scope(
        self,
        session: AsyncSession,
        principal: VisitorPrincipal,
        *,
        card_slug: str = "",
    ) -> None:
        await set_rls_context(
            session,
            tenant_id=principal.tenant_id,
            company_id=principal.company_id,
            card_slug=card_slug,
        )

    async def _set_staff_scope(self, session: AsyncSession, scope: CrmScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
        )

    def _lead_list_item(
        self,
        lead: Lead,
        card_display_name: str,
        profile: VisitorProfile | None,
    ) -> LeadListItem:
        name = self._decrypt_optional(profile.name_ciphertext) if profile else None
        contact_value: str | None = None
        contact_kind = "text"
        if profile:
            for encrypted, kind in (
                (profile.mobile_ciphertext, "mobile"),
                (profile.email_ciphertext, "email"),
                (profile.wechat_ciphertext, "wechat"),
            ):
                if encrypted:
                    contact_value = self._cipher.decrypt(encrypted)
                    contact_kind = kind
                    break
        return LeadListItem(
            id=lead.id,
            card_id=lead.card_id,
            card_display_name=card_display_name,
            visitor_id=lead.visitor_id,
            conversation_id=lead.conversation_id,
            owner_user_id=lead.owner_user_id,
            status=lead.status.value,
            priority=lead.priority,
            masked_name=mask_value(name or "", kind="name"),
            masked_contact=mask_value(contact_value or "", kind=contact_kind),
            company_name=profile.company_name if profile else None,
            interest_tags=list(lead.interest_tags),
            viewed_at=lead.viewed_at,
            closed_at=lead.closed_at,
            version=lead.version,
            created_at=lead.created_at,
            updated_at=lead.updated_at,
        )

    def _followup_view(self, followup: LeadFollowup) -> LeadFollowupView:
        return LeadFollowupView(
            id=followup.id,
            actor_user_id=followup.actor_user_id,
            followup_type=followup.followup_type,
            content=(
                "[已根据访客隐私请求删除]"
                if followup.encryption_key_ref == "erased"
                else self._cipher.decrypt(followup.content_ciphertext)
            ),
            next_at=followup.next_at,
            created_at=followup.created_at,
        )

    @staticmethod
    def _privacy_view(record: PrivacyRequest) -> PrivacyRequestView:
        return PrivacyRequestView(
            id=record.id,
            visitor_id=record.visitor_id,
            request_type=record.request_type.value,
            status=record.status.value,
            verification_method=record.verification_method,
            handled_by=record.handled_by,
            completed_at=record.completed_at,
            evidence=record.evidence,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _card_filters(scope: CrmScope) -> tuple[object, ...]:
        if scope.is_card_owner:
            return (Card.owner_user_id == scope.actor_user_id,)
        return ()

    def _encrypt_optional(self, value: str | None) -> bytes | None:
        return self._cipher.encrypt(value) if value else None

    def _decrypt_optional(self, value: bytes | None) -> str | None:
        return self._cipher.decrypt(value) if value else None

    def _hmac_optional(self, value: str | None) -> str | None:
        return self._cipher.hmac(value) if value else None


def _policy_version(card: Card, scope: ConsentScope) -> str:
    settings = card.settings if isinstance(card.settings, dict) else {}
    policies = settings.get("policy_versions", {})
    if not isinstance(policies, dict):
        policies = {}
    if scope == ConsentScope.CHAT_NOTICE:
        return str(policies.get("chat_notice") or "chat-notice-v1")
    if scope == ConsentScope.BROWSE_NOTICE:
        return str(policies.get("privacy") or "privacy-v1")
    if scope == ConsentScope.PROFILE_PERSONALIZATION:
        return str(
            policies.get("profile_personalization") or "profile-personalization-v1"
        )
    return str(policies.get("lead_consent") or "lead-consent-v1")


__all__ = ["CrmScope", "CrmStore"]
