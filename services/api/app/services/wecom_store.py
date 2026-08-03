from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import (
    AuthSession,
    Card,
    CardKind,
    Lead,
    LeadStatus,
    LifecycleStatus,
    Membership,
    Notification,
    OutboxEvent,
    OutboxStatus,
    Visitor,
    WeComCallbackEvent,
    WeComCardContactWay,
    WeComCustomerLink,
    WeComUserBinding,
)
from app.db.session import set_rls_context
from app.integrations.wecom import WeComMember
from app.integrations.wecom_oauth import WeComOAuthState
from app.services.audit import append_audit


@dataclass(frozen=True, slots=True)
class WeComResolvedIdentity:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    account_hash: str


@dataclass(frozen=True, slots=True)
class WeComCardContactRecord:
    id: uuid.UUID
    card_id: uuid.UUID
    owner_user_id: uuid.UUID
    qr_code_url: str | None
    provisioned_at: datetime


@dataclass(frozen=True, slots=True)
class WeComContactProvisioning:
    card_id: uuid.UUID
    owner_user_id: uuid.UUID
    binding_id: uuid.UUID
    card_display_name: str
    wecom_user_id: str
    state: str
    existing: WeComCardContactRecord | None = None


class WeComStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._cipher = PiiCipher.from_settings(settings)

    async def bind_member(
        self,
        *,
        state: WeComOAuthState,
        member: WeComMember,
        trace_id: str | None,
    ) -> WeComUserBinding:
        if (
            state.mode != "bind"
            or state.user_id is None
            or state.membership_id is None
            or state.session_id is None
        ):
            raise ApiError(400, "WECOM_BIND_STATE_INVALID", "企业微信绑定状态无效")
        now = datetime.now(UTC)
        corp_hash = self._corp_hash()
        user_hash = self.user_hash(member.user_id)
        profile = json.dumps(
            {
                "name": member.name,
                "department_ids": list(member.departments),
                "position": member.position,
                "avatar_url": member.avatar_url,
                "status": member.status,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=state.tenant_id,
                company_id=state.company_id,
            )
            active_session = await session.scalar(
                select(AuthSession.id).where(
                    AuthSession.id == state.session_id,
                    AuthSession.user_id == state.user_id,
                    AuthSession.tenant_id == state.tenant_id,
                    AuthSession.company_id == state.company_id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
            )
            membership = await session.scalar(
                select(Membership).where(
                    Membership.id == state.membership_id,
                    Membership.user_id == state.user_id,
                    Membership.tenant_id == state.tenant_id,
                    Membership.company_id == state.company_id,
                    Membership.status == LifecycleStatus.ACTIVE,
                )
            )
            if active_session is None or membership is None:
                raise ApiError(401, "AUTH_REQUIRED", "员工登录状态无效，请重新登录")

            provider_binding = await session.scalar(
                select(WeComUserBinding)
                .where(
                    WeComUserBinding.tenant_id == state.tenant_id,
                    WeComUserBinding.company_id == state.company_id,
                    WeComUserBinding.corp_id_hmac == corp_hash,
                    WeComUserBinding.wecom_user_id_hmac == user_hash,
                    WeComUserBinding.revoked_at.is_(None),
                )
                .with_for_update()
            )
            membership_binding = await session.scalar(
                select(WeComUserBinding)
                .where(
                    WeComUserBinding.tenant_id == state.tenant_id,
                    WeComUserBinding.company_id == state.company_id,
                    WeComUserBinding.membership_id == state.membership_id,
                )
                .with_for_update()
            )
            if (
                provider_binding is not None
                and provider_binding.membership_id != state.membership_id
            ):
                raise ApiError(
                    409,
                    "WECOM_MEMBER_ALREADY_BOUND",
                    "该企业微信成员已绑定其他后台账号",
                )
            binding = membership_binding or provider_binding
            if binding is None:
                binding = WeComUserBinding(
                    id=uuid.uuid4(),
                    tenant_id=state.tenant_id,
                    company_id=state.company_id,
                    user_id=state.user_id,
                    membership_id=state.membership_id,
                    corp_id_hmac=corp_hash,
                    wecom_user_id_ciphertext=self._cipher.encrypt(member.user_id),
                    wecom_user_id_hmac=user_hash,
                    profile_ciphertext=self._cipher.encrypt(profile),
                    encryption_key_ref=self._cipher.key_ref,
                    last_synced_at=now,
                )
                session.add(binding)
            else:
                binding.user_id = state.user_id
                binding.corp_id_hmac = corp_hash
                binding.wecom_user_id_ciphertext = self._cipher.encrypt(member.user_id)
                binding.wecom_user_id_hmac = user_hash
                binding.profile_ciphertext = self._cipher.encrypt(profile)
                binding.encryption_key_ref = self._cipher.key_ref
                binding.last_synced_at = now
                binding.revoked_at = None
            await append_audit(
                session,
                tenant_id=state.tenant_id,
                company_id=state.company_id,
                actor_user_id=state.user_id,
                action="wecom.identity.bound",
                resource_type="wecom_user_binding",
                resource_id=binding.id,
                trace_id=trace_id,
                event_data={
                    "membership_id": str(state.membership_id),
                    "wecom_user_id_hmac": user_hash,
                    "member_status": member.status,
                },
            )
            await session.flush()
            return binding

    async def resolve_identity(self, *, wecom_user_id: str) -> WeComResolvedIdentity:
        tenant_id, company_id = self._scope()
        user_hash = self.user_hash(wecom_user_id)
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
            )
            binding = await session.scalar(
                select(WeComUserBinding).where(
                    WeComUserBinding.tenant_id == tenant_id,
                    WeComUserBinding.company_id == company_id,
                    WeComUserBinding.corp_id_hmac == self._corp_hash(),
                    WeComUserBinding.wecom_user_id_hmac == user_hash,
                    WeComUserBinding.revoked_at.is_(None),
                )
            )
            if binding is None:
                raise ApiError(
                    403,
                    "WECOM_ACCOUNT_NOT_BOUND",
                    "该企业微信账号尚未绑定后台账号",
                )
            return WeComResolvedIdentity(
                user_id=binding.user_id,
                membership_id=binding.membership_id,
                tenant_id=binding.tenant_id,
                company_id=binding.company_id,
                account_hash=user_hash,
            )

    async def prepare_card_contact_way(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        card_id: uuid.UUID,
        card_owner_only: bool,
    ) -> WeComContactProvisioning:
        """Resolve a card owner and binding before the provider call is made."""

        async with self._sessions() as session, session.begin():
            await set_rls_context(session, tenant_id=tenant_id, company_id=company_id)
            card_filters = (
                Card.tenant_id == tenant_id,
                Card.company_id == company_id,
                Card.id == card_id,
                Card.deleted_at.is_(None),
            )
            if card_owner_only:
                card_filters += (Card.owner_user_id == actor_user_id,)
            card = await session.scalar(select(Card).where(*card_filters))
            if card is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "员工名片不存在")
            if card.card_kind != CardKind.EMPLOYEE or card.owner_user_id is None:
                raise ApiError(422, "WECOM_EMPLOYEE_CARD_REQUIRED", "仅员工名片可绑定企微联系人")

            existing = await session.scalar(
                select(WeComCardContactWay).where(
                    WeComCardContactWay.tenant_id == tenant_id,
                    WeComCardContactWay.company_id == company_id,
                    WeComCardContactWay.card_id == card.id,
                    WeComCardContactWay.revoked_at.is_(None),
                )
            )
            if existing is not None:
                return WeComContactProvisioning(
                    card_id=card.id,
                    owner_user_id=existing.owner_user_id,
                    binding_id=existing.binding_id,
                    card_display_name=card.display_name,
                    wecom_user_id="",
                    state="",
                    existing=self._contact_record(existing),
                )

            binding = await session.scalar(
                select(WeComUserBinding).where(
                    WeComUserBinding.tenant_id == tenant_id,
                    WeComUserBinding.company_id == company_id,
                    WeComUserBinding.user_id == card.owner_user_id,
                    WeComUserBinding.revoked_at.is_(None),
                )
            )
            if binding is None:
                raise ApiError(
                    409,
                    "WECOM_CARD_OWNER_NOT_BOUND",
                    "请先让该名片员工绑定企业微信账号",
                )
            return WeComContactProvisioning(
                card_id=card.id,
                owner_user_id=card.owner_user_id,
                binding_id=binding.id,
                card_display_name=card.display_name,
                wecom_user_id=self._cipher.decrypt(binding.wecom_user_id_ciphertext),
                # WeCom limits this field to 30 bytes. A 24-character opaque token
                # carries no internal identifiers and leaves protocol headroom.
                state=secrets.token_hex(12),
            )

    async def save_card_contact_way(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        provisioning: WeComContactProvisioning,
        config_id: str,
        qr_code_url: str | None,
        trace_id: str | None,
    ) -> WeComCardContactRecord:
        async with self._sessions() as session, session.begin():
            await set_rls_context(session, tenant_id=tenant_id, company_id=company_id)
            existing = await session.scalar(
                select(WeComCardContactWay)
                .where(
                    WeComCardContactWay.tenant_id == tenant_id,
                    WeComCardContactWay.company_id == company_id,
                    WeComCardContactWay.card_id == provisioning.card_id,
                    WeComCardContactWay.revoked_at.is_(None),
                )
                .with_for_update()
            )
            if existing is not None:
                return self._contact_record(existing)
            now = datetime.now(UTC)
            contact = WeComCardContactWay(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                company_id=company_id,
                card_id=provisioning.card_id,
                binding_id=provisioning.binding_id,
                owner_user_id=provisioning.owner_user_id,
                state_token_hmac=self.state_hash(provisioning.state),
                config_id_ciphertext=self._cipher.encrypt(config_id),
                config_id_hmac=self._cipher.hmac(f"wecom-contact-config:{config_id}"),
                qr_code_url_ciphertext=(
                    self._cipher.encrypt(qr_code_url) if qr_code_url else None
                ),
                encryption_key_ref=self._cipher.key_ref,
                provisioned_at=now,
            )
            session.add(contact)
            await append_audit(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
                actor_user_id=actor_user_id,
                action="wecom.card_contact_way.provisioned",
                resource_type="wecom_card_contact_way",
                resource_id=contact.id,
                trace_id=trace_id,
                event_data={
                    "card_id": str(provisioning.card_id),
                    "owner_user_id": str(provisioning.owner_user_id),
                    "binding_id": str(provisioning.binding_id),
                },
            )
            await session.flush()
            return self._contact_record(contact)

    async def get_card_contact_way(
        self,
        *,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        card_id: uuid.UUID,
        card_owner_only: bool,
    ) -> WeComCardContactRecord | None:
        async with self._sessions() as session, session.begin():
            await set_rls_context(session, tenant_id=tenant_id, company_id=company_id)
            filters = [
                WeComCardContactWay.tenant_id == tenant_id,
                WeComCardContactWay.company_id == company_id,
                WeComCardContactWay.card_id == card_id,
                WeComCardContactWay.revoked_at.is_(None),
            ]
            if card_owner_only:
                filters.append(WeComCardContactWay.owner_user_id == actor_user_id)
            contact = await session.scalar(select(WeComCardContactWay).where(*filters))
            return self._contact_record(contact) if contact is not None else None

    async def record_callback(
        self,
        *,
        xml: bytes,
        fields: dict[str, str],
    ) -> bool:
        tenant_id, company_id = self._scope()
        event_type = (fields.get("Event") or fields.get("MsgType") or "unknown").casefold()
        change_type = fields.get("ChangeType")
        event_source = "|".join(
            (
                fields.get("MsgId", ""),
                fields.get("ToUserName", ""),
                fields.get("FromUserName", ""),
                fields.get("CreateTime", ""),
                event_type,
                change_type or "",
                fields.get("EventKey", ""),
                hashlib.sha256(xml).hexdigest(),
            )
        )
        event_key = self._cipher.hmac(f"wecom-event:{event_source}")
        statement = (
            insert(WeComCallbackEvent)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                company_id=company_id,
                corp_id_hmac=self._corp_hash(),
                provider_event_key=event_key,
                event_type=event_type[:80],
                change_type=change_type[:80] if change_type else None,
                payload_ciphertext=self._cipher.encrypt_bytes(xml),
                encryption_key_ref=self._cipher.key_ref,
                status="received",
                attempts=0,
                received_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(
                constraint="uq_wecom_callback_events_provider_key"
            )
            .returning(WeComCallbackEvent.id)
        )
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
            )
            event_id = await session.scalar(statement)
            if event_id is None:
                return False
            event = await session.get(WeComCallbackEvent, event_id)
            if event is None:
                raise RuntimeError("wecom callback event disappeared")
            await self._process_callback_event(session, event=event, fields=fields)
            return True

    async def _process_callback_event(
        self,
        session: AsyncSession,
        *,
        event: WeComCallbackEvent,
        fields: dict[str, str],
    ) -> None:
        event.attempts += 1
        event_name = (fields.get("Event") or "").casefold()
        change_type = (fields.get("ChangeType") or "").casefold()
        if event_name != "change_external_contact" or change_type != "add_external_contact":
            self._finish_callback(event)
            return

        state = (fields.get("State") or "").strip()
        wecom_user_id = (fields.get("UserID") or "").strip()
        external_user_id = (fields.get("ExternalUserID") or "").strip()
        if not state or not wecom_user_id or not external_user_id:
            self._finish_callback(event, error_code="WECOM_ATTRIBUTION_FIELDS_MISSING")
            return

        contact = await session.scalar(
            select(WeComCardContactWay)
            .where(
                WeComCardContactWay.tenant_id == event.tenant_id,
                WeComCardContactWay.company_id == event.company_id,
                WeComCardContactWay.state_token_hmac == self.state_hash(state),
                WeComCardContactWay.revoked_at.is_(None),
            )
            .with_for_update()
        )
        binding = await session.scalar(
            select(WeComUserBinding).where(
                WeComUserBinding.tenant_id == event.tenant_id,
                WeComUserBinding.company_id == event.company_id,
                WeComUserBinding.corp_id_hmac == self._corp_hash(),
                WeComUserBinding.wecom_user_id_hmac == self.user_hash(wecom_user_id),
                WeComUserBinding.revoked_at.is_(None),
            )
        )
        if (
            contact is None
            or binding is None
            or contact.binding_id != binding.id
            or contact.owner_user_id != binding.user_id
        ):
            self._finish_callback(event, error_code="WECOM_ATTRIBUTION_NOT_FOUND")
            return

        now = datetime.now(UTC)
        external_hash = self.external_user_hash(external_user_id)
        visitor_hash = self._cipher.hmac(
            f"visitor:wecom-external:{self._settings.wecom_corp_id}:{external_user_id}"
        )
        visitor_id = uuid.uuid4()
        visitor_statement = (
            insert(Visitor)
            .values(
                id=visitor_id,
                tenant_id=event.tenant_id,
                company_id=event.company_id,
                anonymous_hash=visitor_hash,
                first_seen_at=now,
                last_seen_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_visitors_scope_anonymous_hash",
                set_={"last_seen_at": now},
            )
            .returning(Visitor.id)
        )
        visitor_id = await session.scalar(visitor_statement)
        if visitor_id is None:
            raise RuntimeError("wecom visitor upsert failed")

        link_id = uuid.uuid4()
        link_statement = (
            insert(WeComCustomerLink)
            .values(
                id=link_id,
                tenant_id=event.tenant_id,
                company_id=event.company_id,
                card_id=contact.card_id,
                contact_way_id=contact.id,
                binding_id=binding.id,
                owner_user_id=contact.owner_user_id,
                external_user_id_ciphertext=self._cipher.encrypt(external_user_id),
                external_user_id_hmac=external_hash,
                lead_id=None,
                encryption_key_ref=self._cipher.key_ref,
                added_at=now,
            )
            .on_conflict_do_nothing(
                constraint="uq_wecom_customer_links_owner_external"
            )
            .returning(WeComCustomerLink.id)
        )
        inserted_link_id = await session.scalar(link_statement)
        if inserted_link_id is None:
            contact.last_used_at = now
            self._finish_callback(event)
            return

        lead = Lead(
            id=uuid.uuid4(),
            tenant_id=event.tenant_id,
            company_id=event.company_id,
            card_id=contact.card_id,
            visitor_id=visitor_id,
            conversation_id=None,
            owner_user_id=contact.owner_user_id,
            status=LeadStatus.NEW,
            priority="medium",
            requirement_ciphertext=self._cipher.encrypt(
                "客户通过企业微信名片联系入口添加了负责人，等待进一步沟通。"
            ),
            encryption_key_ref=self._cipher.key_ref,
            interest_tags=["企业微信新增客户"],
        )
        session.add(lead)
        link = await session.get(WeComCustomerLink, inserted_link_id)
        if link is None:
            raise RuntimeError("wecom customer attribution disappeared")
        link.lead_id = lead.id
        contact.last_used_at = now
        session.add(
            Notification(
                id=uuid.uuid4(),
                tenant_id=event.tenant_id,
                company_id=event.company_id,
                recipient_user_id=contact.owner_user_id,
                notification_type="lead_created",
                title="企业微信收到新客户",
                body="客户已通过你的名片添加企业微信，请及时跟进。",
                resource_type="lead",
                resource_id=lead.id,
            )
        )
        session.add(
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=event.tenant_id,
                company_id=event.company_id,
                aggregate_type="lead",
                aggregate_id=lead.id,
                aggregate_version=1,
                event_type="lead.created.v1",
                payload={
                    "lead_id": str(lead.id),
                    "card_id": str(contact.card_id),
                    "owner_user_id": str(contact.owner_user_id),
                },
                headers={"contains_pii": False, "source": "wecom_contact_way"},
                deduplication_key=f"lead.created:{lead.id}",
                status=OutboxStatus.PENDING,
            )
        )
        await append_audit(
            session,
            tenant_id=event.tenant_id,
            company_id=event.company_id,
            actor_user_id=contact.owner_user_id,
            action="wecom.external_contact.attributed",
            resource_type="lead",
            resource_id=lead.id,
            trace_id=f"wecom-callback:{event.id}",
            event_data={
                "card_id": str(contact.card_id),
                "contact_way_id": str(contact.id),
                "binding_id": str(binding.id),
            },
        )
        self._finish_callback(event)

    @staticmethod
    def _finish_callback(
        event: WeComCallbackEvent,
        *,
        error_code: str | None = None,
    ) -> None:
        event.status = "failed" if error_code else "processed"
        event.last_error_code = error_code
        event.processed_at = datetime.now(UTC)

    def _contact_record(self, contact: WeComCardContactWay) -> WeComCardContactRecord:
        return WeComCardContactRecord(
            id=contact.id,
            card_id=contact.card_id,
            owner_user_id=contact.owner_user_id,
            qr_code_url=(
                self._cipher.decrypt(contact.qr_code_url_ciphertext)
                if contact.qr_code_url_ciphertext
                else None
            ),
            provisioned_at=contact.provisioned_at,
        )

    def user_hash(self, wecom_user_id: str) -> str:
        return self._cipher.hmac(
            f"wecom-user:{self._settings.wecom_corp_id}:{wecom_user_id}"
        )

    def state_hash(self, state: str) -> str:
        return self._cipher.hmac(f"wecom-contact-state:{state}")

    def external_user_hash(self, external_user_id: str) -> str:
        return self._cipher.hmac(
            f"wecom-external:{self._settings.wecom_corp_id}:{external_user_id}"
        )

    def _corp_hash(self) -> str:
        corp_id = self._settings.wecom_corp_id
        if not corp_id:
            raise ApiError(409, "WECOM_NOT_CONFIGURED", "企业微信尚未完成配置")
        return self._cipher.hmac(f"wecom-corp:{corp_id}")

    def _scope(self) -> tuple[uuid.UUID, uuid.UUID]:
        tenant_id = self._settings.wecom_tenant_id
        company_id = self._settings.wecom_company_id
        if tenant_id is None or company_id is None:
            raise ApiError(409, "WECOM_NOT_CONFIGURED", "企业微信尚未完成企业范围配置")
        return tenant_id, company_id


__all__ = [
    "WeComCardContactRecord",
    "WeComContactProvisioning",
    "WeComResolvedIdentity",
    "WeComStore",
]
