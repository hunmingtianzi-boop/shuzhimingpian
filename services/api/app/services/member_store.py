from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.member_schemas import (
    BulkMemberRequest,
    BulkMemberResult,
    BulkMemberRow,
    BulkMemberRowResult,
    BulkMemberSummary,
    MemberRecord,
    MemberRowError,
    PasswordResetRecord,
    UpdateMemberAccessRequest,
    UpdateSelfProfileRequest,
)
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.core.staff_auth import hash_staff_password, normalize_staff_account
from app.db.models import (
    AuthSession,
    LifecycleStatus,
    Membership,
    MembershipRole,
    StaffCredential,
    User,
)
from app.db.session import set_rls_context
from app.services.audit import append_audit
from app.services.catalog_store import card_asset_belongs_to_company


@dataclass(frozen=True, slots=True)
class MemberScope:
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    actor_user_id: uuid.UUID
    actor_session_id: uuid.UUID
    actor_role: str = MembershipRole.COMPANY_ADMIN.value
    actor_permissions: tuple[str, ...] = ()

    @property
    def is_admin(self) -> bool:
        return self.actor_role in {
            MembershipRole.COMPANY_ADMIN.value,
            MembershipRole.PLATFORM_ADMIN.value,
        }


_DEFAULT_PERMISSIONS: dict[MembershipRole, tuple[str, ...]] = {
    MembershipRole.COMPANY_ADMIN: (
        "analytics.read",
        "card.manage",
        "catalog.manage",
        "company.manage",
        "conversations.read",
        "knowledge.manage",
        "knowledge.publish",
        "leads.read",
        "leads.write",
        "members.manage",
        "privacy.manage",
        "summaries.write",
    ),
    MembershipRole.CARD_OWNER: (
        "analytics.read",
        "card.read",
        "card.write",
        "catalog.read",
        "conversations.read",
        "leads.read",
        "leads.write",
    ),
}


class MemberStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._cipher = PiiCipher.from_settings(settings)

    async def create_member(
        self,
        *,
        scope: MemberScope,
        row: BulkMemberRow,
        trace_id: str | None,
    ) -> MemberRecord:
        try:
            self._authorize_row(scope, row)
        except _RowConflict as exc:
            raise ApiError(403, exc.code, exc.message) from exc
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"staff-account:{row.account}"},
            )
            credential = await session.scalar(
                select(StaffCredential.id).where(
                    StaffCredential.account_normalized == row.account
                )
            )
            if credential is not None:
                raise ApiError(409, "ACCOUNT_CONFLICT", "The account is unavailable.")
            try:
                member = await self._create_row(session, scope=scope, row=row)
                await append_audit(
                    session,
                    tenant_id=scope.tenant_id,
                    company_id=scope.company_id,
                    actor_user_id=scope.actor_user_id,
                    action="company.member.create",
                    resource_type="membership",
                    resource_id=member.membership_id,
                    trace_id=trace_id,
                    event_data={
                        "role": member.role,
                        "status": member.status,
                        "account_hmac": self._cipher.hmac(member.account),
                    },
                )
                return member
            except _RowConflict as exc:
                raise ApiError(409, exc.code, exc.message) from exc
            except IntegrityError as exc:
                raise ApiError(
                    409,
                    "MEMBER_CONFLICT",
                    "The account or contact information conflicts with an existing member.",
                ) from exc

    async def bulk_upsert(
        self,
        *,
        scope: MemberScope,
        body: BulkMemberRequest,
        trace_id: str | None,
    ) -> BulkMemberResult:
        batch_id = uuid.uuid4()
        results: list[BulkMemberRowResult] = []
        first_rows: dict[str, int] = {}
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            for row_number, raw_row in enumerate(body.rows, start=1):
                account = _safe_account(raw_row.get("account"))
                try:
                    row = BulkMemberRow.model_validate(raw_row)
                except ValidationError as exc:
                    results.append(_validation_failure(row_number, account, exc))
                    continue
                try:
                    self._authorize_row(scope, row)
                except _RowConflict as exc:
                    results.append(
                        BulkMemberRowResult(
                            row_number=row_number,
                            account=row.account,
                            outcome="failed",
                            error=MemberRowError(
                                code=exc.code,
                                message=exc.message,
                                fields=list(exc.fields),
                            ),
                        )
                    )
                    continue

                duplicate_of = first_rows.get(row.account)
                if duplicate_of is not None:
                    results.append(
                        BulkMemberRowResult(
                            row_number=row_number,
                            account=row.account,
                            outcome="duplicate",
                            duplicate_of_row=duplicate_of,
                            error=MemberRowError(
                                code="DUPLICATE_BATCH_ACCOUNT",
                                message="The account already appeared earlier in this batch.",
                                fields=["account"],
                            ),
                        )
                    )
                    continue
                first_rows[row.account] = row_number

                try:
                    async with session.begin_nested():
                        outcome, member = await self._upsert_row(
                            session,
                            scope=scope,
                            row=row,
                        )
                    results.append(
                        BulkMemberRowResult(
                            row_number=row_number,
                            account=row.account,
                            outcome=outcome,
                            member=member,
                        )
                    )
                except _RowConflict as exc:
                    results.append(
                        BulkMemberRowResult(
                            row_number=row_number,
                            account=row.account,
                            outcome="failed",
                            error=MemberRowError(
                                code=exc.code,
                                message=exc.message,
                                fields=list(exc.fields),
                            ),
                        )
                    )
                except ApiError as exc:
                    results.append(
                        BulkMemberRowResult(
                            row_number=row_number,
                            account=row.account,
                            outcome="failed",
                            error=MemberRowError(
                                code=exc.code,
                                message=exc.safe_message,
                            ),
                        )
                    )
                except IntegrityError:
                    results.append(
                        BulkMemberRowResult(
                            row_number=row_number,
                            account=row.account,
                            outcome="failed",
                            error=MemberRowError(
                                code="MEMBER_CONFLICT",
                                message=(
                                    "The account or contact information conflicts with "
                                    "an existing member."
                                ),
                            ),
                        )
                    )

            summary = _summarize(results)
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="company.members.bulk_upsert",
                resource_type="member_batch",
                resource_id=batch_id,
                trace_id=trace_id,
                event_data={
                    "batch_id": batch_id,
                    **summary.model_dump(),
                    "failure_codes": [
                        result.error.code for result in results if result.error is not None
                    ],
                },
            )
        return BulkMemberResult(batch_id=batch_id, summary=summary, rows=results)

    async def list_members(
        self,
        *,
        scope: MemberScope,
        limit: int,
        offset: int,
    ) -> tuple[list[MemberRecord], int]:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            filters = (
                Membership.tenant_id == scope.tenant_id,
                Membership.company_id == scope.company_id,
                # This endpoint is the enterprise employee directory. Platform
                # operators can hold a scoped membership for access control, but
                # they are not employees and the public response contract must
                # never project platform_admin as a company member.
                Membership.role.in_(
                    (MembershipRole.COMPANY_ADMIN, MembershipRole.CARD_OWNER)
                ),
            )
            total = int(
                await session.scalar(select(func.count(Membership.id)).where(*filters)) or 0
            )
            statement = (
                select(Membership, User, StaffCredential)
                .join(User, User.id == Membership.user_id)
                .join(StaffCredential, StaffCredential.membership_id == Membership.id)
                .where(*filters)
                .order_by(Membership.created_at, Membership.id)
                .limit(limit)
                .offset(offset)
            )
            rows = (await session.execute(statement)).all()
            return [
                _member_record(membership, user, credential, self._cipher)
                for membership, user, credential in rows
            ], total

    async def get_member(
        self,
        *,
        scope: MemberScope,
        membership_id: uuid.UUID,
    ) -> MemberRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            membership, user, credential = await self._member_row(
                session,
                scope=scope,
                membership_id=membership_id,
            )
            return _member_record(membership, user, credential, self._cipher)

    async def update_self_profile(
        self,
        *,
        scope: MemberScope,
        membership_id: uuid.UUID,
        body: UpdateSelfProfileRequest,
        trace_id: str | None,
    ) -> MemberRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            membership, user, credential = await self._member_row(
                session,
                scope=scope,
                membership_id=membership_id,
                for_update=True,
            )
            self._authorize_self_profile_target(
                scope,
                membership=membership,
                user=user,
                credential=credential,
            )
            self._validate_self_avatar(scope, body.avatar_url)
            previous_avatar = membership.avatar_url
            membership.avatar_url = body.avatar_url or None
            await session.flush()
            await _refresh_member_timestamps(session, membership, user, credential)
            member = _member_record(membership, user, credential, self._cipher)
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="company.member.self_profile_update",
                resource_type="membership",
                resource_id=membership.id,
                trace_id=trace_id,
                event_data={"avatar_changed": previous_avatar != member.avatar_url},
            )
            return member

    @staticmethod
    def _authorize_self_profile_target(
        scope: MemberScope,
        *,
        membership: Membership,
        user: User,
        credential: StaffCredential,
    ) -> None:
        if (
            membership.user_id != scope.actor_user_id
            or membership.status != LifecycleStatus.ACTIVE
            or user.status != LifecycleStatus.ACTIVE
            or user.deleted_at is not None
            or not credential.is_enabled
        ):
            raise ApiError(
                403,
                "SELF_PROFILE_UNAVAILABLE",
                "The current active company membership is required.",
            )

    @staticmethod
    def _validate_self_avatar(scope: MemberScope, avatar_url: str | None) -> None:
        if avatar_url is None:
            return
        if not card_asset_belongs_to_company(avatar_url, scope.company_id):
            raise ApiError(
                422,
                "SELF_AVATAR_ASSET_OUT_OF_SCOPE",
                "头像必须来自当前企业的名片素材库",
            )

    async def update_access(
        self,
        *,
        scope: MemberScope,
        membership_id: uuid.UUID,
        body: UpdateMemberAccessRequest,
        trace_id: str | None,
    ) -> MemberRecord:
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._acquire_company_admin_guard(session, scope=scope)
            membership, user, credential = await self._member_row(
                session,
                scope=scope,
                membership_id=membership_id,
                for_update=True,
            )
            before = {
                "display_name": user.display_name,
                "job_title": membership.job_title,
                "avatar_url": membership.avatar_url,
                "business_summary": membership.business_summary,
                "public_positioning": membership.public_positioning,
                "identity_titles": list(membership.identity_titles),
                "professional_tags": list(membership.professional_tags),
                "email_hmac": user.email_hmac,
                "mobile_hmac": user.mobile_hmac,
                "role": membership.role.value,
                "permissions": list(membership.permissions),
            }
            desired_role = MembershipRole(body.role) if body.role is not None else membership.role
            try:
                self._authorize_target(
                    scope,
                    membership=membership,
                    desired_role=desired_role,
                )
                self._authorize_permissions(
                    scope,
                    body.permissions if body.permissions is not None else membership.permissions,
                )
            except _RowConflict as exc:
                raise ApiError(403, exc.code, exc.message) from exc
            await self._guard_admin_transition(
                session,
                scope=scope,
                membership=membership,
                credential=credential,
                desired_role=desired_role,
                desired_status=membership.status,
            )
            if body.display_name is not None:
                user.display_name = body.display_name
            if "job_title" in body.model_fields_set:
                membership.job_title = body.job_title or None
            if "avatar_url" in body.model_fields_set:
                membership.avatar_url = body.avatar_url or None
            if "business_summary" in body.model_fields_set:
                membership.business_summary = body.business_summary or None
            if "public_positioning" in body.model_fields_set:
                membership.public_positioning = body.public_positioning or None
            if body.identity_titles is not None:
                membership.identity_titles = list(body.identity_titles)
            if body.professional_tags is not None:
                membership.professional_tags = list(body.professional_tags)
            if "email" in body.model_fields_set:
                user.email_hmac = self._cipher.hmac(body.email) if body.email else None
                user.email_ciphertext = self._cipher.encrypt(body.email) if body.email else None
            if "mobile" in body.model_fields_set:
                user.mobile_hmac = self._cipher.hmac(body.mobile) if body.mobile else None
                user.mobile_ciphertext = self._cipher.encrypt(body.mobile) if body.mobile else None
            if body.role is not None:
                membership.role = desired_role
            if body.permissions is not None:
                membership.permissions = sorted(dict.fromkeys(body.permissions))
            try:
                await session.flush()
            except IntegrityError as exc:
                raise ApiError(
                    409,
                    "MEMBER_CONFLICT",
                    "The email or mobile number conflicts with an existing member.",
                ) from exc
            await _refresh_member_timestamps(session, membership, user, credential)
            member = _member_record(membership, user, credential, self._cipher)
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="company.member.access_update",
                resource_type="membership",
                resource_id=membership.id,
                trace_id=trace_id,
                event_data={
                    "before_role": before["role"],
                    "before_permissions": before["permissions"],
                    "after_role": member.role,
                    "after_permissions": member.permissions,
                    "display_name_changed": before["display_name"] != member.display_name,
                    "identity_profile_changed": any(
                        before[field] != getattr(member, field)
                        for field in ("job_title", "avatar_url", "business_summary")
                    ),
                    "contact_info_changed": (
                        before["email_hmac"] != user.email_hmac
                        or before["mobile_hmac"] != user.mobile_hmac
                    ),
                },
            )
            return member

    async def reset_password(
        self,
        *,
        scope: MemberScope,
        membership_id: uuid.UUID,
        password: str,
        revoke_sessions: bool,
        trace_id: str | None,
    ) -> PasswordResetRecord:
        if not revoke_sessions:
            raise ApiError(
                422,
                "SESSION_REVOCATION_REQUIRED",
                "Password reset must revoke all active member sessions.",
            )
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            membership, _user, credential = await self._member_row(
                session,
                scope=scope,
                membership_id=membership_id,
                for_update=True,
            )
            self._authorize_target(
                scope,
                membership=membership,
                desired_role=membership.role,
            )
            changed_at = datetime.now(UTC)
            credential.password_hash = hash_staff_password(password)
            credential.password_changed_at = changed_at
            credential.failed_attempts = 0
            credential.locked_until = None
            credential.last_failed_at = None
            sessions_revoked = 0
            if revoke_sessions:
                result = await session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.user_id == membership.user_id,
                        AuthSession.tenant_id == scope.tenant_id,
                        AuthSession.company_id == scope.company_id,
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(
                        revoked_at=changed_at,
                        revoke_reason="password_reset_by_admin",
                    )
                )
                sessions_revoked = int(result.rowcount or 0)
            await session.flush()
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="company.member.password_reset",
                resource_type="membership",
                resource_id=membership.id,
                trace_id=trace_id,
                event_data={
                    "sessions_revoked": sessions_revoked,
                    "revoke_sessions": revoke_sessions,
                },
            )
            return PasswordResetRecord(
                membership_id=membership.id,
                password_changed_at=changed_at,
                sessions_revoked=sessions_revoked,
            )

    async def set_status(
        self,
        *,
        scope: MemberScope,
        membership_id: uuid.UUID,
        status: str,
        trace_id: str | None,
    ) -> MemberRecord:
        desired = LifecycleStatus(status)
        async with self._sessions() as session, session.begin():
            await self._set_scope(session, scope)
            await self._acquire_company_admin_guard(session, scope=scope)
            membership, user, credential = await self._member_row(
                session,
                scope=scope,
                membership_id=membership_id,
                for_update=True,
            )
            self._authorize_target(
                scope,
                membership=membership,
                desired_role=membership.role,
            )
            changed = membership.status != desired or credential.is_enabled != (
                desired == LifecycleStatus.ACTIVE
            )
            await self._guard_admin_transition(
                session,
                scope=scope,
                membership=membership,
                credential=credential,
                desired_role=membership.role,
                desired_status=desired,
            )
            membership.status = desired
            credential.is_enabled = desired == LifecycleStatus.ACTIVE
            if desired == LifecycleStatus.ACTIVE:
                credential.failed_attempts = 0
                credential.locked_until = None
                credential.last_failed_at = None
            else:
                await self._revoke_sessions(
                    session,
                    scope=scope,
                    user_id=membership.user_id,
                    reason="member_disabled",
                )
            await session.flush()
            await _refresh_member_timestamps(session, membership, user, credential)
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="company.member.status_update",
                resource_type="membership",
                resource_id=membership.id,
                trace_id=trace_id,
                event_data={"status": desired.value, "changed": changed},
            )
            return _member_record(membership, user, credential, self._cipher)

    async def _member_row(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
        membership_id: uuid.UUID,
        for_update: bool = False,
    ) -> tuple[Membership, User, StaffCredential]:
        statement = (
            select(Membership, User, StaffCredential)
            .join(User, User.id == Membership.user_id)
            .join(StaffCredential, StaffCredential.membership_id == Membership.id)
            .where(
                Membership.id == membership_id,
                Membership.tenant_id == scope.tenant_id,
                Membership.company_id == scope.company_id,
            )
        )
        if for_update:
            statement = statement.with_for_update()
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            raise ApiError(
                404,
                "MEMBER_NOT_FOUND",
                "The member does not exist in the current company scope.",
            )
        membership, user, credential = row
        return membership, user, credential

    async def _upsert_row(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
        row: BulkMemberRow,
    ) -> tuple[str, MemberRecord]:
        await self._acquire_company_admin_guard(session, scope=scope)
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"staff-account:{row.account}"},
        )
        credential = await session.scalar(
            select(StaffCredential)
            .where(StaffCredential.account_normalized == row.account)
            .with_for_update()
        )
        if credential is None:
            return "created", await self._create_row(session, scope=scope, row=row)
        if credential.tenant_id != scope.tenant_id or credential.company_id != scope.company_id:
            raise _RowConflict(
                "ACCOUNT_CONFLICT",
                "The account is unavailable.",
                ("account",),
            )
        scoped = (
            await session.execute(
                select(Membership, User)
                .join(User, User.id == Membership.user_id)
                .where(
                    Membership.id == credential.membership_id,
                    Membership.user_id == credential.user_id,
                    Membership.tenant_id == scope.tenant_id,
                    Membership.company_id == scope.company_id,
                )
                .with_for_update()
            )
        ).one_or_none()
        if scoped is None:
            raise _RowConflict(
                "ACCOUNT_CONFLICT",
                "The account is unavailable.",
                ("account",),
            )
        membership, user = scoped
        self._authorize_target(
            scope,
            membership=membership,
            desired_role=MembershipRole(row.role),
        )
        await self._guard_admin_transition(
            session,
            scope=scope,
            membership=membership,
            credential=credential,
            desired_role=MembershipRole(row.role),
            desired_status=LifecycleStatus(row.status),
        )
        changed = await self._apply_updates(
            session,
            scope=scope,
            row=row,
            membership=membership,
            user=user,
            credential=credential,
        )
        await session.flush()
        await _refresh_member_timestamps(session, membership, user, credential)
        return ("updated" if changed else "unchanged"), _member_record(
            membership, user, credential, self._cipher
        )

    async def _create_row(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
        row: BulkMemberRow,
    ) -> MemberRecord:
        email_hmac = self._cipher.hmac(row.email) if row.email else None
        mobile_hmac = self._cipher.hmac(row.mobile) if row.mobile else None
        await self._ensure_contacts_available(
            session,
            email_hmac=email_hmac,
            mobile_hmac=mobile_hmac,
        )
        role = MembershipRole(row.role)
        desired_status = LifecycleStatus(row.status)
        user = User(
            id=uuid.uuid4(),
            display_name=row.display_name,
            email_ciphertext=self._cipher.encrypt(row.email) if row.email else None,
            email_hmac=email_hmac,
            mobile_ciphertext=self._cipher.encrypt(row.mobile) if row.mobile else None,
            mobile_hmac=mobile_hmac,
            status=LifecycleStatus.ACTIVE,
        )
        membership = Membership(
            id=uuid.uuid4(),
            user_id=user.id,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            role=role,
            permissions=_permissions(row, role),
            job_title=row.job_title,
            avatar_url=row.avatar_url,
            business_summary=row.business_summary,
            public_positioning=row.public_positioning,
            identity_titles=list(row.identity_titles),
            professional_tags=list(row.professional_tags),
            status=desired_status,
        )
        credential = StaffCredential(
            id=uuid.uuid4(),
            user_id=user.id,
            membership_id=membership.id,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            account_normalized=row.account,
            password_hash=hash_staff_password(row.password.get_secret_value()),
            is_enabled=desired_status == LifecycleStatus.ACTIVE,
        )
        if (
            role == MembershipRole.COMPANY_ADMIN
            and desired_status != LifecycleStatus.ACTIVE
        ):
            raise _RowConflict(
                "INACTIVE_ADMIN_NOT_ALLOWED",
                "A company administrator must be created in active status.",
                ("role", "status"),
            )
        session.add(user)
        await session.flush()
        session.add(membership)
        await session.flush()
        session.add(credential)
        await session.flush()
        await _refresh_member_timestamps(session, membership, user, credential)
        return _member_record(membership, user, credential, self._cipher)

    async def _apply_updates(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
        row: BulkMemberRow,
        membership: Membership,
        user: User,
        credential: StaffCredential,
    ) -> bool:
        """Update identity fields; passwords rotate only with rotate_password=true."""
        email_hmac = self._cipher.hmac(row.email) if row.email else None
        mobile_hmac = self._cipher.hmac(row.mobile) if row.mobile else None
        await self._ensure_contacts_available(
            session,
            email_hmac=email_hmac,
            mobile_hmac=mobile_hmac,
            exclude_user_id=user.id,
        )
        role = MembershipRole(row.role)
        permissions = _permissions(row, role)
        desired_status = LifecycleStatus(row.status)
        desired_enabled = desired_status == LifecycleStatus.ACTIVE
        changed = False

        updates = [
            (
                user.display_name,
                row.display_name,
                lambda value: setattr(user, "display_name", value),
            ),
            (membership.role, role, lambda value: setattr(membership, "role", value)),
            (
                tuple(membership.permissions),
                tuple(permissions),
                lambda value: setattr(membership, "permissions", list(value)),
            ),
            (
                membership.status,
                desired_status,
                lambda value: setattr(membership, "status", value),
            ),
            (
                credential.is_enabled,
                desired_enabled,
                lambda value: setattr(credential, "is_enabled", value),
            ),
        ]
        identity_updates = (
            ("job_title", row.job_title),
            ("avatar_url", row.avatar_url),
            ("business_summary", row.business_summary),
            ("public_positioning", row.public_positioning),
            ("identity_titles", list(row.identity_titles)),
            ("professional_tags", list(row.professional_tags)),
        )
        for field, desired in identity_updates:
            if field in row.model_fields_set:
                updates.append(
                    (
                        getattr(membership, field, None),
                        desired,
                        lambda value, field=field: setattr(membership, field, value),
                    )
                )

        for current, desired, setter in updates:
            if current != desired:
                setter(desired)
                changed = True

        if user.email_hmac != email_hmac:
            user.email_hmac = email_hmac
            user.email_ciphertext = self._cipher.encrypt(row.email) if row.email else None
            changed = True
        if user.mobile_hmac != mobile_hmac:
            user.mobile_hmac = mobile_hmac
            user.mobile_ciphertext = self._cipher.encrypt(row.mobile) if row.mobile else None
            changed = True
        if desired_enabled:
            if credential.failed_attempts or credential.locked_until or credential.last_failed_at:
                credential.failed_attempts = 0
                credential.locked_until = None
                credential.last_failed_at = None
                changed = True
        if row.rotate_password and not desired_enabled:
            raise _RowConflict(
                "PASSWORD_ROTATION_REQUIRES_ACTIVE_MEMBER",
                "Password rotation requires an active member.",
                ("rotate_password", "status"),
            )
        if not desired_enabled:
            await self._revoke_sessions(
                session,
                scope=scope,
                user_id=user.id,
                reason="member_disabled",
            )
        if row.rotate_password:
            credential.password_hash = hash_staff_password(row.password.get_secret_value())
            credential.password_changed_at = datetime.now(UTC)
            credential.failed_attempts = 0
            credential.locked_until = None
            credential.last_failed_at = None
            await self._revoke_sessions(
                session,
                scope=scope,
                user_id=user.id,
                reason="password_rotated_by_bulk_import",
            )
            changed = True
        return changed

    async def _ensure_contacts_available(
        self,
        session: AsyncSession,
        *,
        email_hmac: str | None,
        mobile_hmac: str | None,
        exclude_user_id: uuid.UUID | None = None,
    ) -> None:
        filters = []
        if email_hmac is not None:
            filters.append(User.email_hmac == email_hmac)
        if mobile_hmac is not None:
            filters.append(User.mobile_hmac == mobile_hmac)
        if not filters:
            return
        statement = select(User.id).where(or_(*filters))
        if exclude_user_id is not None:
            statement = statement.where(User.id != exclude_user_id)
        if await session.scalar(statement.limit(1)) is not None:
            raise _RowConflict(
                "CONTACT_CONFLICT",
                "The email address or mobile number is unavailable.",
                ("email", "mobile"),
            )

    async def _revoke_sessions(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
        user_id: uuid.UUID,
        reason: str,
    ) -> None:
        await session.execute(
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.tenant_id == scope.tenant_id,
                AuthSession.company_id == scope.company_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC), revoke_reason=reason)
        )

    async def _require_other_active_company_admin(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
        exclude_membership_id: uuid.UUID,
    ) -> None:
        await self._acquire_company_admin_guard(session, scope=scope)
        other_admin = await session.scalar(
            select(Membership.id)
            .join(StaffCredential, StaffCredential.membership_id == Membership.id)
            .where(
                Membership.tenant_id == scope.tenant_id,
                Membership.company_id == scope.company_id,
                Membership.id != exclude_membership_id,
                Membership.role == MembershipRole.COMPANY_ADMIN,
                Membership.status == LifecycleStatus.ACTIVE,
                StaffCredential.is_enabled.is_(True),
            )
            .limit(1)
        )
        if other_admin is None:
            raise ApiError(
                409,
                "LAST_COMPANY_ADMIN_REQUIRED",
                "At least one active company administrator must remain.",
            )

    async def _acquire_company_admin_guard(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
    ) -> None:
        # Take the company lock before any member/account row lock. Every path
        # that can remove an active administrator follows this order, avoiding
        # advisory-lock/row-lock cycles under concurrent mutations.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"company-admin-guard:{scope.tenant_id}:{scope.company_id}"},
        )

    async def _guard_admin_transition(
        self,
        session: AsyncSession,
        *,
        scope: MemberScope,
        membership: Membership,
        credential: StaffCredential,
        desired_role: MembershipRole,
        desired_status: LifecycleStatus,
    ) -> None:
        if (
            membership.role == MembershipRole.COMPANY_ADMIN
            and membership.status == LifecycleStatus.ACTIVE
            and credential.is_enabled
            and (
                desired_role != MembershipRole.COMPANY_ADMIN
                or desired_status != LifecycleStatus.ACTIVE
            )
        ):
            await self._require_other_active_company_admin(
                session,
                scope=scope,
                exclude_membership_id=membership.id,
            )

    async def _set_scope(self, session: AsyncSession, scope: MemberScope) -> None:
        await set_rls_context(
            session,
            tenant_id=scope.tenant_id,
            company_id=scope.company_id,
            actor_user_id=scope.actor_user_id,
            actor_session_id=scope.actor_session_id,
        )

    def _authorize_row(self, scope: MemberScope, row: BulkMemberRow) -> None:
        role = MembershipRole(row.role)
        self._authorize_role(scope, role)
        self._authorize_permissions(scope, _permissions(row, role))

    def _authorize_target(
        self,
        scope: MemberScope,
        *,
        membership: Membership,
        desired_role: MembershipRole,
    ) -> None:
        if not scope.is_admin and (
            membership.role == MembershipRole.COMPANY_ADMIN
            or desired_role == MembershipRole.COMPANY_ADMIN
        ):
            raise ApiError(
                403,
                "ADMIN_MEMBER_MANAGEMENT_FORBIDDEN",
                "Only an administrator can manage company administrators.",
            )
        self._authorize_role(scope, desired_role)

    def _authorize_role(self, scope: MemberScope, desired_role: MembershipRole) -> None:
        if not scope.is_admin and desired_role == MembershipRole.COMPANY_ADMIN:
            raise _RowConflict(
                "ADMIN_ROLE_ASSIGNMENT_FORBIDDEN",
                "Only an administrator can assign the company administrator role.",
                ("role",),
            )

    def _authorize_permissions(self, scope: MemberScope, permissions: list[str]) -> None:
        if scope.is_admin:
            return
        unauthorized = sorted(set(permissions) - set(scope.actor_permissions))
        if unauthorized:
            raise _RowConflict(
                "PERMISSION_DELEGATION_FORBIDDEN",
                "A delegated member manager cannot grant permissions they do not hold.",
                ("permissions",),
            )


class _RowConflict(Exception):
    def __init__(self, code: str, message: str, fields: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields


def _permissions(row: BulkMemberRow, role: MembershipRole) -> list[str]:
    selected = row.permissions
    if selected is None:
        selected = list(_DEFAULT_PERMISSIONS[role])
    return sorted(dict.fromkeys(selected))


def _safe_account(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return normalize_staff_account(value)
    except ValueError:
        return value.strip()[:200] or None


def _validation_failure(
    row_number: int,
    account: str | None,
    exc: ValidationError,
) -> BulkMemberRowResult:
    fields = sorted(
        {
            str(error["loc"][0])
            for error in exc.errors()
            if error.get("loc") and isinstance(error["loc"][0], (str, int))
        }
    )
    return BulkMemberRowResult(
        row_number=row_number,
        account=account,
        outcome="failed",
        error=MemberRowError(
            code="ROW_VALIDATION_FAILED",
            message="The row contains invalid or missing member fields.",
            fields=fields,
        ),
    )


def _summarize(results: list[BulkMemberRowResult]) -> BulkMemberSummary:
    counts = {outcome: 0 for outcome in ("created", "updated", "unchanged", "duplicate", "failed")}
    for result in results:
        counts[result.outcome] += 1
    return BulkMemberSummary(
        total=len(results),
        succeeded=counts["created"] + counts["updated"] + counts["unchanged"],
        created=counts["created"],
        updated=counts["updated"],
        unchanged=counts["unchanged"],
        duplicated=counts["duplicate"],
        failed=counts["failed"],
    )


def _member_record(
    membership: Membership,
    user: User,
    credential: StaffCredential,
    cipher: PiiCipher,
) -> MemberRecord:
    timestamps = [membership.updated_at, user.updated_at, credential.updated_at]
    return MemberRecord(
        membership_id=membership.id,
        user_id=user.id,
        account=credential.account_normalized,
        display_name=user.display_name,
        job_title=membership.job_title,
        avatar_url=membership.avatar_url,
        business_summary=membership.business_summary,
        public_positioning=membership.public_positioning,
        identity_titles=list(membership.identity_titles),
        professional_tags=list(membership.professional_tags),
        email=cipher.decrypt(user.email_ciphertext) if user.email_ciphertext else None,
        mobile=cipher.decrypt(user.mobile_ciphertext) if user.mobile_ciphertext else None,
        role=membership.role.value,
        permissions=list(membership.permissions),
        status=membership.status.value,
        credential_enabled=credential.is_enabled,
        created_at=membership.created_at,
        updated_at=max(timestamps),
    )


async def _refresh_member_timestamps(
    session: AsyncSession,
    membership: Membership,
    user: User,
    credential: StaffCredential,
) -> None:
    """Reload timestamps changed by PostgreSQL triggers without implicit async I/O."""

    for model in (membership, user, credential):
        await session.refresh(model, attribute_names=["created_at", "updated_at"])


__all__ = ["MemberScope", "MemberStore"]
