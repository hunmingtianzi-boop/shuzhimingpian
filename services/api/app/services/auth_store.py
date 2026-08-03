from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.request_security import account_subject_hash
from app.core.staff_auth import normalize_staff_account, verify_staff_password_or_dummy
from app.core.tokens import (
    IssuedStaffTokens,
    StaffPrincipal,
    StaffRefreshPrincipal,
    StaffTokenError,
    decode_staff_refresh_token,
    hash_refresh_token,
    issue_staff_tokens,
)
from app.db.models import (
    AuthSession,
    Company,
    LifecycleStatus,
    Membership,
    SecurityEvent,
    StaffCredential,
    Tenant,
    User,
)
from app.db.session import set_rls_context


@dataclass(frozen=True, slots=True)
class StaffIdentity:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    display_name: str
    role: str
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StaffAuthentication:
    tokens: IssuedStaffTokens
    identity: StaffIdentity


class AuthStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings

    async def login(
        self,
        *,
        account: str,
        credential: str,
        account_hash: str | None = None,
        request_ip_hash: str | None = None,
    ) -> StaffAuthentication:
        account_digest = account_hash or account_subject_hash(self._settings, account)
        try:
            normalized_account = normalize_staff_account(account)
        except ValueError:
            verify_staff_password_or_dummy(credential, None)
            await self.record_security_event(
                event_type="staff.login",
                outcome="failed",
                account_hash=account_digest,
                request_ip_hash=request_ip_hash,
                reason_code="invalid_account_format",
            )
            raise _invalid_credentials() from None

        failure_reason: str | None = None
        failure_outcome = "failed"
        authentication: StaffAuthentication | None = None
        issued_session_id: uuid.UUID | None = None
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            staff_credential = await session.scalar(
                select(StaffCredential)
                .where(StaffCredential.account_normalized == normalized_account)
                .with_for_update()
            )
            password_valid = verify_staff_password_or_dummy(
                credential,
                staff_credential.password_hash if staff_credential else None,
            )
            if staff_credential is None:
                failure_reason = "account_not_found"
            else:
                locked = bool(
                    staff_credential.locked_until and staff_credential.locked_until > now
                )
                if staff_credential.locked_until and not locked:
                    staff_credential.failed_attempts = 0
                    staff_credential.locked_until = None

                if not staff_credential.is_enabled:
                    failure_reason = "credential_disabled"
                    failure_outcome = "blocked"
                elif locked:
                    failure_reason = "credential_locked"
                    failure_outcome = "blocked"
                elif not password_valid:
                    if not locked:
                        self._record_failed_attempt(staff_credential, now)
                    failure_reason = "invalid_credential"
                else:
                    await set_rls_context(
                        session,
                        tenant_id=staff_credential.tenant_id,
                        company_id=staff_credential.company_id,
                    )
                    identity = await self._load_active_identity(
                        session,
                        user_id=staff_credential.user_id,
                        membership_id=staff_credential.membership_id,
                        tenant_id=staff_credential.tenant_id,
                        company_id=staff_credential.company_id,
                    )
                    if identity is None:
                        self._record_failed_attempt(staff_credential, now)
                        failure_reason = "identity_inactive"
                    else:
                        staff_credential.failed_attempts = 0
                        staff_credential.locked_until = None
                        staff_credential.last_failed_at = None
                        staff_credential.last_authenticated_at = now
                        session_id = uuid.uuid4()
                        issued_session_id = session_id
                        tokens = self._issue_tokens(identity, session_id=session_id)
                        session.add(
                            AuthSession(
                                id=session_id,
                                user_id=identity.user_id,
                                tenant_id=identity.tenant_id,
                                company_id=identity.company_id,
                                refresh_token_hash=hash_refresh_token(tokens.refresh_token),
                                expires_at=datetime.fromtimestamp(
                                    tokens.refresh_expires_at,
                                    tz=UTC,
                                ),
                            )
                        )
                        authentication = StaffAuthentication(tokens=tokens, identity=identity)

            identity = authentication.identity if authentication is not None else None
            session.add(
                _security_event(
                    event_type="staff.login",
                    outcome="succeeded" if authentication is not None else failure_outcome,
                    account_hash=account_digest,
                    request_ip_hash=request_ip_hash,
                    reason_code=failure_reason,
                    user_id=(
                        identity.user_id
                        if identity
                        else getattr(staff_credential, "user_id", None)
                    ),
                    membership_id=(
                        identity.membership_id
                        if identity
                        else getattr(staff_credential, "membership_id", None)
                    ),
                    tenant_id=(
                        identity.tenant_id
                        if identity
                        else getattr(staff_credential, "tenant_id", None)
                    ),
                    company_id=(
                        identity.company_id
                        if identity
                        else getattr(staff_credential, "company_id", None)
                    ),
                    session_id=issued_session_id,
                )
            )

        if authentication is None:
            raise _invalid_credentials()
        return authentication

    async def refresh(
        self,
        refresh_token: str,
        *,
        request_ip_hash: str | None = None,
    ) -> StaffAuthentication:
        try:
            principal = decode_staff_refresh_token(
                refresh_token,
                signing_key=self._settings.jwt_signing_key.get_secret_value(),
                issuer=self._settings.app_name,
            )
        except StaffTokenError as exc:
            await self.record_security_event(
                event_type="staff.refresh",
                outcome="failed",
                request_ip_hash=request_ip_hash,
                reason_code="token_invalid",
            )
            raise _invalid_refresh() from exc

        failure_reason: str | None = None
        failure_outcome = "failed"
        authentication: StaffAuthentication | None = None
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
            )
            auth_session = await self._load_session_for_update(session, principal)
            if auth_session is None:
                failure_reason = "session_not_found"
            elif auth_session.revoked_at is not None:
                failure_reason = "session_revoked"
            elif auth_session.expires_at <= now:
                auth_session.revoked_at = now
                auth_session.revoke_reason = "refresh_expired"
                failure_reason = "refresh_expired"
            elif not hmac.compare_digest(
                auth_session.refresh_token_hash,
                hash_refresh_token(refresh_token),
            ):
                auth_session.revoked_at = now
                auth_session.revoke_reason = "refresh_reuse_detected"
                failure_reason = "refresh_reuse_detected"
                failure_outcome = "blocked"
            else:
                identity = await self._load_active_identity(
                    session,
                    user_id=principal.user_id,
                    membership_id=principal.membership_id,
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                )
                if identity is None:
                    auth_session.revoked_at = now
                    auth_session.revoke_reason = "membership_inactive"
                    failure_reason = "membership_inactive"
                    failure_outcome = "blocked"
                else:
                    tokens = self._issue_tokens(identity, session_id=auth_session.id)
                    auth_session.refresh_token_hash = hash_refresh_token(tokens.refresh_token)
                    auth_session.expires_at = datetime.fromtimestamp(
                        tokens.refresh_expires_at,
                        tz=UTC,
                    )
                    authentication = StaffAuthentication(tokens=tokens, identity=identity)

            session.add(
                _security_event(
                    event_type="staff.refresh",
                    outcome="succeeded" if authentication is not None else failure_outcome,
                    request_ip_hash=request_ip_hash,
                    reason_code=failure_reason,
                    user_id=principal.user_id,
                    membership_id=principal.membership_id,
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    session_id=principal.session_id,
                )
            )

        if authentication is None:
            raise _invalid_refresh()
        return authentication

    async def logout(
        self,
        principal: StaffPrincipal,
        *,
        request_ip_hash: str | None = None,
    ) -> None:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
            )
            auth_session = await session.scalar(
                select(AuthSession)
                .where(
                    AuthSession.id == principal.session_id,
                    AuthSession.user_id == principal.user_id,
                    AuthSession.tenant_id == principal.tenant_id,
                    AuthSession.company_id == principal.company_id,
                )
                .with_for_update()
            )
            if auth_session is not None and auth_session.revoked_at is None:
                auth_session.revoked_at = now
                auth_session.revoke_reason = "staff_logout"
                outcome = "succeeded"
                reason_code = None
            else:
                outcome = "failed"
                reason_code = "session_not_active"
            session.add(
                _security_event(
                    event_type="staff.logout",
                    outcome=outcome,
                    request_ip_hash=request_ip_hash,
                    reason_code=reason_code,
                    user_id=principal.user_id,
                    membership_id=principal.membership_id,
                    tenant_id=principal.tenant_id,
                    company_id=principal.company_id,
                    session_id=principal.session_id,
                )
            )

    async def record_security_event(
        self,
        *,
        event_type: str,
        outcome: str,
        account_hash: str | None = None,
        request_ip_hash: str | None = None,
        reason_code: str | None = None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                _security_event(
                    event_type=event_type,
                    outcome=outcome,
                    account_hash=account_hash,
                    request_ip_hash=request_ip_hash,
                    reason_code=reason_code,
                )
            )

    async def authenticate_trusted_identity(
        self,
        *,
        user_id: uuid.UUID,
        membership_id: uuid.UUID,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
        event_type: str,
        account_hash: str,
        request_ip_hash: str | None = None,
    ) -> StaffAuthentication:
        """Issue a staff session after a trusted external identity is resolved."""

        authentication: StaffAuthentication | None = None
        issued_session_id: uuid.UUID | None = None
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=tenant_id,
                company_id=company_id,
            )
            identity = await self._load_active_identity(
                session,
                user_id=user_id,
                membership_id=membership_id,
                tenant_id=tenant_id,
                company_id=company_id,
            )
            if identity is not None:
                issued_session_id = uuid.uuid4()
                tokens = self._issue_tokens(identity, session_id=issued_session_id)
                session.add(
                    AuthSession(
                        id=issued_session_id,
                        user_id=identity.user_id,
                        tenant_id=identity.tenant_id,
                        company_id=identity.company_id,
                        refresh_token_hash=hash_refresh_token(tokens.refresh_token),
                        expires_at=datetime.fromtimestamp(
                            tokens.refresh_expires_at,
                            tz=UTC,
                        ),
                    )
                )
                authentication = StaffAuthentication(tokens=tokens, identity=identity)
            session.add(
                _security_event(
                    event_type=event_type,
                    outcome="succeeded" if authentication else "blocked",
                    account_hash=account_hash,
                    request_ip_hash=request_ip_hash,
                    reason_code=None if authentication else "identity_inactive",
                    user_id=user_id,
                    membership_id=membership_id,
                    tenant_id=tenant_id,
                    company_id=company_id,
                    session_id=issued_session_id,
                )
            )
        if authentication is None:
            raise _invalid_credentials()
        return authentication

    async def get_current(self, principal: StaffPrincipal) -> StaffIdentity:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
            )
            auth_session = await session.scalar(
                select(AuthSession).where(
                    AuthSession.id == principal.session_id,
                    AuthSession.user_id == principal.user_id,
                    AuthSession.tenant_id == principal.tenant_id,
                    AuthSession.company_id == principal.company_id,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                )
            )
            if auth_session is None:
                raise _invalid_access()
            identity = await self._load_active_identity(
                session,
                user_id=principal.user_id,
                membership_id=principal.membership_id,
                tenant_id=principal.tenant_id,
                company_id=principal.company_id,
            )
            if identity is None:
                raise _invalid_access()
            return identity

    async def _load_session_for_update(
        self,
        session: AsyncSession,
        principal: StaffRefreshPrincipal,
    ) -> AuthSession | None:
        return await session.scalar(
            select(AuthSession)
            .where(
                AuthSession.id == principal.session_id,
                AuthSession.user_id == principal.user_id,
                AuthSession.tenant_id == principal.tenant_id,
                AuthSession.company_id == principal.company_id,
            )
            .with_for_update()
        )

    async def _load_active_identity(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        membership_id: uuid.UUID,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> StaffIdentity | None:
        membership = await session.scalar(
            select(Membership).where(
                Membership.id == membership_id,
                Membership.user_id == user_id,
                Membership.tenant_id == tenant_id,
                Membership.company_id == company_id,
                Membership.status == LifecycleStatus.ACTIVE,
            )
        )
        if (
            membership is None
            or membership.id != membership_id
            or membership.user_id != user_id
            or membership.tenant_id != tenant_id
            or membership.company_id != company_id
        ):
            return None
        user = await session.scalar(
            select(User).where(
                User.id == user_id,
                User.status == LifecycleStatus.ACTIVE,
                User.deleted_at.is_(None),
            )
        )
        tenant = await session.scalar(
            select(Tenant).where(
                Tenant.id == tenant_id,
                Tenant.status == LifecycleStatus.ACTIVE,
                Tenant.deleted_at.is_(None),
            )
        )
        company = await session.scalar(
            select(Company).where(
                Company.id == company_id,
                Company.tenant_id == tenant_id,
                Company.status == LifecycleStatus.ACTIVE,
                Company.deleted_at.is_(None),
            )
        )
        if (
            user is None
            or user.id != user_id
            or tenant is None
            or tenant.id != tenant_id
            or company is None
            or company.id != company_id
            or company.tenant_id != tenant_id
        ):
            return None
        return StaffIdentity(
            user_id=user.id,
            membership_id=membership.id,
            tenant_id=membership.tenant_id,
            company_id=company_id,
            display_name=user.display_name,
            role=membership.role.value,
            permissions=tuple(dict.fromkeys(membership.permissions)),
        )

    def _record_failed_attempt(
        self,
        credential: StaffCredential,
        now: datetime,
    ) -> None:
        credential.failed_attempts += 1
        credential.last_failed_at = now
        if credential.failed_attempts >= self._settings.staff_login_max_failures:
            credential.locked_until = now + timedelta(
                seconds=self._settings.staff_login_lock_seconds
            )

    def _issue_tokens(
        self,
        identity: StaffIdentity,
        *,
        session_id: uuid.UUID,
    ) -> IssuedStaffTokens:
        return issue_staff_tokens(
            signing_key=self._settings.jwt_signing_key.get_secret_value(),
            issuer=self._settings.app_name,
            access_ttl_seconds=self._settings.access_token_ttl_seconds,
            refresh_ttl_seconds=self._settings.refresh_token_ttl_seconds,
            user_id=identity.user_id,
            membership_id=identity.membership_id,
            tenant_id=identity.tenant_id,
            company_id=identity.company_id,
            role=identity.role,
            permissions=identity.permissions,
            session_id=session_id,
        )


def _security_event(
    *,
    event_type: str,
    outcome: str,
    account_hash: str | None = None,
    request_ip_hash: str | None = None,
    user_id: uuid.UUID | None = None,
    membership_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    company_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    reason_code: str | None = None,
) -> SecurityEvent:
    if outcome not in {"succeeded", "failed", "blocked"}:
        raise ValueError("invalid security event outcome")
    return SecurityEvent(
        id=uuid.uuid4(),
        event_type=event_type[:80],
        outcome=outcome,
        account_hash=_validated_hash(account_hash),
        request_ip_hash=_validated_hash(request_ip_hash),
        user_id=user_id,
        membership_id=membership_id,
        tenant_id=tenant_id,
        company_id=company_id,
        session_id=session_id,
        reason_code=reason_code[:80] if reason_code else None,
        event_data={},
        occurred_at=datetime.now(UTC),
    )


def _validated_hash(value: str | None) -> str | None:
    if value is None:
        return None
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("security audit hashes must be lowercase SHA-256 HMAC hex")
    return value


def _invalid_credentials() -> ApiError:
    return ApiError(401, "INVALID_CREDENTIALS", "账号或凭证不正确")


def _invalid_refresh() -> ApiError:
    return ApiError(401, "INVALID_REFRESH_TOKEN", "刷新凭证无效，请重新登录")


def _invalid_access() -> ApiError:
    return ApiError(401, "AUTH_REQUIRED", "员工登录状态无效，请重新登录")


__all__ = ["AuthStore", "StaffAuthentication", "StaffIdentity"]
