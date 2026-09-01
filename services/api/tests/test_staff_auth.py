from __future__ import annotations

import uuid
from dataclasses import fields
from typing import Any

import pytest

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.staff_auth import (
    hash_staff_password,
    normalize_staff_account,
    verify_staff_password,
)
from app.core.tokens import (
    StaffPrincipal,
    StaffTokenError,
    VisitorTokenError,
    decode_staff_access_token,
    decode_staff_refresh_token,
    decode_visitor_token,
    hash_refresh_token,
    issue_staff_tokens,
    issue_visitor_token,
)
from app.db.models import (
    AuthSession,
    Company,
    LifecycleStatus,
    Membership,
    MembershipRole,
    SecurityEvent,
    StaffCredential,
    Tenant,
    TenantType,
    User,
)
from app.services.auth_store import AuthStore


class _AsyncContext:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    async def __aenter__(self) -> Any:
        return self.value

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeSession:
    def __init__(self, scalar_results: list[Any]) -> None:
        self.scalar_results = list(scalar_results)
        self.operations: list[tuple[str, Any]] = []
        self.added: list[Any] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _AsyncContext:
        return _AsyncContext()

    async def scalar(self, statement: Any) -> Any:
        self.operations.append(("scalar", statement))
        return self.scalar_results.pop(0)

    async def execute(self, statement: Any, parameters: Any = None) -> None:
        self.operations.append(("execute", parameters))

    def add(self, value: Any) -> None:
        self.added.append(value)


class FakeSessionFactory:
    def __init__(self, sessions: list[FakeSession]) -> None:
        self.sessions = list(sessions)

    def __call__(self) -> FakeSession:
        return self.sessions.pop(0)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "app_env": "test",
        "app_name": "staff-auth-test",
        "jwt_signing_key": "s" * 32,
        "access_token_ttl_seconds": 600,
        "refresh_token_ttl_seconds": 7_200,
        "staff_login_max_failures": 3,
        "staff_login_lock_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)


def _identity_rows(*, company_id: uuid.UUID | None = None) -> tuple[Any, ...]:
    tenant_id = uuid.uuid4()
    selected_company_id = company_id or uuid.uuid4()
    user_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    credential = StaffCredential(
        id=uuid.uuid4(),
        user_id=user_id,
        membership_id=membership_id,
        tenant_id=tenant_id,
        company_id=selected_company_id,
        account_normalized="admin@example.test",
        password_hash=hash_staff_password("correct-password"),
        is_enabled=True,
        failed_attempts=0,
    )
    membership = Membership(
        id=membership_id,
        user_id=user_id,
        tenant_id=tenant_id,
        company_id=selected_company_id,
        role=MembershipRole.COMPANY_ADMIN,
        permissions=["card.publish", "knowledge.review"],
        status=LifecycleStatus.ACTIVE,
    )
    user = User(
        id=user_id,
        display_name="测试管理员",
        status=LifecycleStatus.ACTIVE,
    )
    tenant = Tenant(
        id=tenant_id,
        slug="test-tenant",
        name="测试租户",
        tenant_type=TenantType.ENTERPRISE,
        status=LifecycleStatus.ACTIVE,
    )
    company = Company(
        id=selected_company_id,
        tenant_id=tenant_id,
        name="测试企业",
        normalized_name="测试企业",
        status=LifecycleStatus.ACTIVE,
    )
    return credential, membership, user, tenant, company


def test_scrypt_password_hash_is_salted_and_strictly_verified() -> None:
    first = hash_staff_password("correct-password")
    second = hash_staff_password("correct-password")

    assert first.startswith("scrypt$16384$8$1$")
    assert first != second
    assert verify_staff_password("correct-password", first)
    assert not verify_staff_password("wrong-password", first)
    assert not verify_staff_password("correct-password", "malformed")
    assert normalize_staff_account("  Admin@Example.TEST ") == "admin@example.test"


def test_staff_principal_has_the_stable_admin_dependency_shape() -> None:
    assert tuple(field.name for field in fields(StaffPrincipal)) == (
        "user_id",
        "membership_id",
        "tenant_id",
        "company_id",
        "role",
        "permissions",
        "session_id",
        "token_id",
    )


def test_staff_tokens_have_distinct_access_refresh_and_visitor_boundaries() -> None:
    ids = {
        name: uuid.uuid4()
        for name in ("user_id", "membership_id", "tenant_id", "company_id", "session_id")
    }
    tokens = issue_staff_tokens(
        signing_key="s" * 32,
        issuer="test",
        access_ttl_seconds=600,
        refresh_ttl_seconds=3_600,
        role="company_admin",
        permissions=("card.publish",),
        **ids,
    )
    access = decode_staff_access_token(tokens.access_token, signing_key="s" * 32, issuer="test")
    refresh = decode_staff_refresh_token(
        tokens.refresh_token,
        signing_key="s" * 32,
        issuer="test",
    )

    assert access.user_id == ids["user_id"]
    assert access.permissions == ("card.publish",)
    assert refresh.session_id == ids["session_id"]
    with pytest.raises(StaffTokenError):
        decode_staff_access_token(tokens.refresh_token, signing_key="s" * 32, issuer="test")
    with pytest.raises(StaffTokenError):
        decode_staff_refresh_token(tokens.access_token, signing_key="s" * 32, issuer="test")

    visitor_token, _ = issue_visitor_token(
        signing_key="s" * 32,
        issuer="test",
        ttl_seconds=600,
        visitor_id=uuid.uuid4(),
        visit_id=uuid.uuid4(),
        tenant_id=ids["tenant_id"],
        company_id=ids["company_id"],
        card_id=uuid.uuid4(),
    )
    with pytest.raises(StaffTokenError):
        decode_staff_access_token(visitor_token, signing_key="s" * 32, issuer="test")
    with pytest.raises(VisitorTokenError):
        decode_visitor_token(tokens.access_token, signing_key="s" * 32, issuer="test")


@pytest.mark.asyncio
async def test_login_sets_credential_scope_before_membership_and_stores_only_refresh_hash() -> None:
    credential, membership, user, tenant, company = _identity_rows()
    session = FakeSession([credential, membership, credential, user, tenant, company])
    store = AuthStore(FakeSessionFactory([session]), _settings())  # type: ignore[arg-type]

    result = await store.login(
        account="ADMIN@example.test",
        credential="correct-password",
    )

    assert [operation for operation, _ in session.operations[:2]] == ["scalar", "execute"]
    assert session.operations[1][1] == {
        "tenant_id": str(credential.tenant_id),
        "company_id": str(credential.company_id),
        "card_slug": "",
        "actor_user_id": "",
        "actor_session_id": "",
    }
    assert len(session.added) == 2
    auth_session = next(item for item in session.added if isinstance(item, AuthSession))
    security_event = next(item for item in session.added if isinstance(item, SecurityEvent))
    assert isinstance(auth_session, AuthSession)
    assert auth_session.refresh_token_hash == hash_refresh_token(result.tokens.refresh_token)
    assert result.tokens.refresh_token not in auth_session.refresh_token_hash
    assert result.identity.company_id == credential.company_id
    assert security_event.event_type == "staff.login"
    assert security_event.outcome == "succeeded"
    assert len(security_event.account_hash or "") == 64
    assert credential.account_normalized not in repr(security_event.__dict__)
    assert "correct-password" not in repr(security_event.__dict__)


@pytest.mark.asyncio
async def test_wrong_password_counts_failures_locks_and_keeps_error_uniform() -> None:
    credential, *_ = _identity_rows()
    sessions = [FakeSession([credential]) for _ in range(4)]
    store = AuthStore(FakeSessionFactory(sessions), _settings())  # type: ignore[arg-type]

    errors = []
    for supplied in ("wrong-one", "wrong-two", "wrong-three", "correct-password"):
        with pytest.raises(ApiError) as captured:
            await store.login(account=credential.account_normalized, credential=supplied)
        errors.append((captured.value.status_code, captured.value.code))

    assert errors == [(401, "INVALID_CREDENTIALS")] * 4
    assert credential.failed_attempts == 3
    assert credential.locked_until is not None
    outcomes = [
        next(item for item in session.added if isinstance(item, SecurityEvent)).outcome
        for session in sessions
    ]
    assert outcomes == ["failed", "failed", "failed", "blocked"]

    unknown_session = FakeSession([None])
    unknown = AuthStore(
        FakeSessionFactory([unknown_session]),  # type: ignore[arg-type]
        _settings(),
    )
    with pytest.raises(ApiError) as unknown_error:
        await unknown.login(account="unknown@example.test", credential="anything")
    assert unknown_error.value.code == "INVALID_CREDENTIALS"
    unknown_event = next(item for item in unknown_session.added if isinstance(item, SecurityEvent))
    assert unknown_event.reason_code == "account_not_found"
    assert "unknown@example.test" not in repr(unknown_event.__dict__)
    assert "anything" not in repr(unknown_event.__dict__)


@pytest.mark.asyncio
async def test_cross_company_membership_is_rejected_after_scope_resolution() -> None:
    credential, membership, *_ = _identity_rows()
    membership.company_id = uuid.uuid4()
    session = FakeSession([credential, membership, credential])
    store = AuthStore(FakeSessionFactory([session]), _settings())  # type: ignore[arg-type]

    with pytest.raises(ApiError) as captured:
        await store.login(
            account=credential.account_normalized,
            credential="correct-password",
        )

    assert captured.value.code == "INVALID_CREDENTIALS"
    assert len(session.added) == 1
    assert isinstance(session.added[0], SecurityEvent)
    assert session.added[0].reason_code == "identity_inactive"


@pytest.mark.asyncio
async def test_refresh_rotates_hash_and_replay_revokes_the_session() -> None:
    credential, membership, user, tenant, company = _identity_rows()
    login_session = FakeSession(
        [credential, membership, credential, user, tenant, company]
    )
    settings = _settings()
    login_store = AuthStore(FakeSessionFactory([login_session]), settings)  # type: ignore[arg-type]
    login = await login_store.login(
        account=credential.account_normalized,
        credential="correct-password",
    )
    auth_session = next(item for item in login_session.added if isinstance(item, AuthSession))

    refresh_session = FakeSession(
        [auth_session, membership, credential, user, tenant, company]
    )
    refresh_store = AuthStore(
        FakeSessionFactory([refresh_session]),  # type: ignore[arg-type]
        settings,
    )
    rotated = await refresh_store.refresh(login.tokens.refresh_token)

    assert rotated.tokens.refresh_token != login.tokens.refresh_token
    assert auth_session.refresh_token_hash == hash_refresh_token(rotated.tokens.refresh_token)

    replay_session = FakeSession([auth_session])
    replay_store = AuthStore(FakeSessionFactory([replay_session]), settings)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as captured:
        await replay_store.refresh(login.tokens.refresh_token)

    assert captured.value.code == "INVALID_REFRESH_TOKEN"
    assert auth_session.revoke_reason == "refresh_reuse_detected"
    assert auth_session.revoked_at is not None
    replay_event = next(item for item in replay_session.added if isinstance(item, SecurityEvent))
    assert replay_event.outcome == "blocked"
    assert replay_event.reason_code == "refresh_reuse_detected"


@pytest.mark.asyncio
async def test_invalid_refresh_is_audited_without_storing_the_token() -> None:
    session = FakeSession([])
    store = AuthStore(FakeSessionFactory([session]), _settings())  # type: ignore[arg-type]
    raw_token = "synthetic-invalid-refresh-token"  # noqa: S105 - negative test canary

    with pytest.raises(ApiError) as captured:
        await store.refresh(raw_token)

    assert captured.value.code == "INVALID_REFRESH_TOKEN"
    event = next(item for item in session.added if isinstance(item, SecurityEvent))
    assert event.event_type == "staff.refresh"
    assert event.reason_code == "token_invalid"
    assert raw_token not in repr(event.__dict__)


@pytest.mark.asyncio
async def test_logout_revokes_the_exact_scoped_session() -> None:
    credential, membership, user, tenant, company = _identity_rows()
    login_session = FakeSession(
        [credential, membership, credential, user, tenant, company]
    )
    settings = _settings()
    login_store = AuthStore(FakeSessionFactory([login_session]), settings)  # type: ignore[arg-type]
    login = await login_store.login(
        account=credential.account_normalized,
        credential="correct-password",
    )
    principal = decode_staff_access_token(
        login.tokens.access_token,
        signing_key=settings.jwt_signing_key.get_secret_value(),
        issuer=settings.app_name,
    )
    auth_session = next(item for item in login_session.added if isinstance(item, AuthSession))
    logout_session = FakeSession([auth_session])
    logout_store = AuthStore(
        FakeSessionFactory([logout_session]),  # type: ignore[arg-type]
        settings,
    )

    await logout_store.logout(principal)

    assert auth_session.revoked_at is not None
    assert auth_session.revoke_reason == "staff_logout"
    assert logout_session.operations[0][0] == "execute"
    assert logout_session.operations[0][1]["company_id"] == str(principal.company_id)
    logout_event = next(item for item in logout_session.added if isinstance(item, SecurityEvent))
    assert logout_event.event_type == "staff.logout"
    assert logout_event.outcome == "succeeded"
