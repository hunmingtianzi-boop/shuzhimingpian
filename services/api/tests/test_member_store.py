from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr, ValidationError

from app.api.errors import ApiError
from app.api.member_schemas import (
    BulkMemberRow,
    UpdateMemberAccessRequest,
    UpdateSelfProfileRequest,
)
from app.core.pii import PiiCipher
from app.db.models import LifecycleStatus, MembershipRole
from app.services.member_store import MemberScope, MemberStore, _RowConflict


def _row(**updates: object) -> BulkMemberRow:
    values: dict[str, object] = {
        "account": "member-user",
        "display_name": "Example Member",
        "password": SecretStr("Member-Password-2026!"),
        "role": "card_owner",
        "status": "active",
    }
    values.update(updates)
    return BulkMemberRow(**values)


def _scope() -> MemberScope:
    return MemberScope(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        actor_session_id=uuid.uuid4(),
    )


def _delegated_scope(*permissions: str) -> MemberScope:
    scope = _scope()
    return MemberScope(
        tenant_id=scope.tenant_id,
        company_id=scope.company_id,
        actor_user_id=scope.actor_user_id,
        actor_session_id=scope.actor_session_id,
        actor_role=MembershipRole.CARD_OWNER.value,
        actor_permissions=tuple(permissions),
    )


def test_permissions_are_restricted_to_company_allowlist() -> None:
    accepted = _row(permissions=["members.manage", "knowledge.publish"])

    assert accepted.permissions == ["knowledge.publish", "members.manage"]
    for permission in ("*", "admin:*", "platform.manage", "made_up.permission"):
        with pytest.raises(ValidationError):
            _row(permissions=[permission])


def test_platform_role_cannot_be_assigned_through_member_input() -> None:
    with pytest.raises(ValidationError):
        _row(role="platform_admin")


def test_member_identity_fields_can_be_explicitly_cleared() -> None:
    body = UpdateMemberAccessRequest(job_title=None, avatar_url=None, business_summary=None)

    assert body.model_fields_set == {"job_title", "avatar_url", "business_summary"}


def test_empty_member_update_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UpdateMemberAccessRequest()


def test_self_profile_contract_only_accepts_a_safe_avatar() -> None:
    assert UpdateSelfProfileRequest(avatar_url="/assets/avatar.webp").avatar_url == (
        "/assets/avatar.webp"
    )
    with pytest.raises(ValidationError):
        UpdateSelfProfileRequest.model_validate(
            {"avatar_url": "/assets/avatar.webp", "membership_id": str(uuid.uuid4())}
        )
    with pytest.raises(ValidationError):
        UpdateSelfProfileRequest(avatar_url="http://127.0.0.1/avatar.webp")


def test_self_profile_target_accepts_only_the_actor_active_membership() -> None:
    scope = _scope()
    store = object.__new__(MemberStore)
    membership = SimpleNamespace(user_id=scope.actor_user_id, status=LifecycleStatus.ACTIVE)
    user = SimpleNamespace(status=LifecycleStatus.ACTIVE, deleted_at=None)
    credential = SimpleNamespace(is_enabled=True)

    store._authorize_self_profile_target(
        scope,
        membership=membership,
        user=user,
        credential=credential,
    )

    for rejected_membership, rejected_user, rejected_credential in (
        (
            SimpleNamespace(user_id=uuid.uuid4(), status=LifecycleStatus.ACTIVE),
            user,
            credential,
        ),
        (
            SimpleNamespace(user_id=scope.actor_user_id, status=LifecycleStatus.DISABLED),
            user,
            credential,
        ),
        (
            membership,
            SimpleNamespace(status=LifecycleStatus.DISABLED, deleted_at=None),
            credential,
        ),
        (membership, user, SimpleNamespace(is_enabled=False)),
    ):
        with pytest.raises(ApiError) as captured:
            store._authorize_self_profile_target(
                scope,
                membership=rejected_membership,
                user=rejected_user,
                credential=rejected_credential,
            )
        assert captured.value.code == "SELF_PROFILE_UNAVAILABLE"


def test_self_profile_avatar_must_belong_to_the_current_company_asset_library() -> None:
    scope = _scope()
    store = object.__new__(MemberStore)
    own_asset = (
        f"/api/v1/public/card-assets/{scope.company_id}/{uuid.uuid4()}.webp"
    )

    store._validate_self_avatar(scope, None)
    store._validate_self_avatar(scope, own_asset)

    for rejected in (
        "https://cdn.example.test/avatar.webp",
        f"/api/v1/public/card-assets/{uuid.uuid4()}/{uuid.uuid4()}.webp",
        f"/api/v1/public/card-assets/{scope.company_id}/avatar.webp",
    ):
        with pytest.raises(ApiError) as captured:
            store._validate_self_avatar(scope, rejected)
        assert captured.value.status_code == 422
        assert captured.value.code == "SELF_AVATAR_ASSET_OUT_OF_SCOPE"


def test_delegated_manager_cannot_create_or_promote_company_admin() -> None:
    store = object.__new__(MemberStore)
    scope = _delegated_scope("members.manage", "card.read")

    with pytest.raises(_RowConflict) as exc:
        store._authorize_row(scope, _row(role="company_admin"))

    assert getattr(exc.value, "code", None) == "ADMIN_ROLE_ASSIGNMENT_FORBIDDEN"


@pytest.mark.asyncio
async def test_single_create_rejects_delegated_admin_promotion_before_database_access() -> None:
    store = object.__new__(MemberStore)
    store._sessions = lambda: pytest.fail("database must not be opened")

    with pytest.raises(ApiError) as exc:
        await store.create_member(
            scope=_delegated_scope("members.manage"),
            row=_row(role="company_admin"),
            trace_id="privilege-escalation-test",
        )

    assert exc.value.status_code == 403
    assert exc.value.code == "ADMIN_ROLE_ASSIGNMENT_FORBIDDEN"


def test_delegated_manager_can_only_grant_permissions_they_hold() -> None:
    store = object.__new__(MemberStore)
    scope = _delegated_scope("members.manage", "card.read")

    store._authorize_row(scope, _row(permissions=["card.read"]))
    with pytest.raises(_RowConflict) as exc:
        store._authorize_row(scope, _row(permissions=["knowledge.publish"]))

    assert getattr(exc.value, "code", None) == "PERMISSION_DELEGATION_FORBIDDEN"


def test_delegated_manager_cannot_modify_disable_or_reset_company_admin() -> None:
    store = object.__new__(MemberStore)
    scope = _delegated_scope("members.manage")
    target = SimpleNamespace(role=MembershipRole.COMPANY_ADMIN)

    with pytest.raises(ApiError) as exc:
        store._authorize_target(
            scope,
            membership=target,
            desired_role=MembershipRole.COMPANY_ADMIN,
        )

    assert exc.value.status_code == 403
    assert exc.value.code == "ADMIN_MEMBER_MANAGEMENT_FORBIDDEN"


@pytest.mark.asyncio
async def test_existing_password_is_not_changed_without_explicit_rotation() -> None:
    store = object.__new__(MemberStore)
    store._cipher = SimpleNamespace(
        hmac=lambda value: f"hmac:{value}",
        encrypt=lambda value: value.encode(),
    )
    store._ensure_contacts_available = AsyncMock()
    store._revoke_sessions = AsyncMock()
    session = AsyncMock()
    now = datetime.now(UTC)
    membership = SimpleNamespace(
        id=uuid.uuid4(),
        role=MembershipRole.CARD_OWNER,
        permissions=["card.read"],
        status=LifecycleStatus.ACTIVE,
        job_title="销售总监",
        avatar_url="https://cdn.example.test/avatar.png",
        business_summary="负责重点客户业务。",
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        display_name="Example Member",
        email_hmac=None,
        email_ciphertext=None,
        mobile_hmac=None,
        mobile_ciphertext=None,
    )
    credential = SimpleNamespace(
        password_hash="original-password-hash",  # noqa: S106
        password_changed_at=now,
        is_enabled=True,
        failed_attempts=0,
        locked_until=None,
        last_failed_at=None,
    )

    changed = await store._apply_updates(
        session,
        scope=_scope(),
        row=_row(permissions=["card.read"]),
        membership=membership,
        user=user,
        credential=credential,
    )

    assert changed is False
    assert credential.password_hash == "original-password-hash"  # noqa: S105
    assert credential.password_changed_at == now
    assert membership.job_title == "销售总监"
    assert membership.avatar_url == "https://cdn.example.test/avatar.png"
    assert membership.business_summary == "负责重点客户业务。"
    store._revoke_sessions.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_bulk_password_rotation_rehashes_and_revokes_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = object.__new__(MemberStore)
    store._cipher = SimpleNamespace(
        hmac=lambda value: f"hmac:{value}",
        encrypt=lambda value: value.encode(),
    )
    store._ensure_contacts_available = AsyncMock()
    store._revoke_sessions = AsyncMock()
    monkeypatch.setattr(
        "app.services.member_store.hash_staff_password",
        lambda password: f"hashed:{password}",
    )
    session = AsyncMock()
    membership = SimpleNamespace(
        id=uuid.uuid4(),
        role=MembershipRole.CARD_OWNER,
        permissions=["card.read"],
        status=LifecycleStatus.ACTIVE,
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        display_name="Example Member",
        email_hmac=None,
        email_ciphertext=None,
        mobile_hmac=None,
        mobile_ciphertext=None,
    )
    credential = SimpleNamespace(
        password_hash="original-password-hash",  # noqa: S106
        password_changed_at=datetime.now(UTC),
        is_enabled=True,
        failed_attempts=3,
        locked_until=datetime.now(UTC),
        last_failed_at=datetime.now(UTC),
    )

    changed = await store._apply_updates(
        session,
        scope=_scope(),
        row=_row(permissions=["card.read"], rotate_password=True),
        membership=membership,
        user=user,
        credential=credential,
    )

    assert changed is True
    assert credential.password_hash == "hashed:Member-Password-2026!"  # noqa: S105
    assert credential.failed_attempts == 0
    assert credential.locked_until is None
    store._revoke_sessions.assert_awaited_once()


@pytest.mark.asyncio
async def test_member_contact_updates_are_encrypted_and_search_hashed() -> None:
    store = object.__new__(MemberStore)
    store._cipher = PiiCipher.from_secret(
        "member-store-test-secret-material-2026",
        key_ref="member-test-v1",
    )
    store._ensure_contacts_available = AsyncMock()
    store._revoke_sessions = AsyncMock()
    session = AsyncMock()
    membership = SimpleNamespace(
        id=uuid.uuid4(),
        role=MembershipRole.CARD_OWNER,
        permissions=["card.read"],
        status=LifecycleStatus.ACTIVE,
    )
    user = SimpleNamespace(
        id=uuid.uuid4(),
        display_name="Example Member",
        email_hmac=None,
        email_ciphertext=None,
        mobile_hmac=None,
        mobile_ciphertext=None,
    )
    credential = SimpleNamespace(
        password_hash="original-password-hash",  # noqa: S106
        password_changed_at=datetime.now(UTC),
        is_enabled=True,
        failed_attempts=0,
        locked_until=None,
        last_failed_at=None,
    )

    changed = await store._apply_updates(
        session,
        scope=_scope(),
        row=_row(
            permissions=["card.read"],
            email="member@example.test",
            mobile="+8613800138000",
        ),
        membership=membership,
        user=user,
        credential=credential,
    )

    assert changed is True
    assert user.email_ciphertext != b"member@example.test"
    assert user.mobile_ciphertext != b"+8613800138000"
    assert store._cipher.decrypt(user.email_ciphertext) == "member@example.test"
    assert store._cipher.decrypt(user.mobile_ciphertext) == "+8613800138000"
    assert user.email_hmac == store._cipher.hmac("member@example.test")
    assert user.mobile_hmac == store._cipher.hmac("+8613800138000")


@pytest.mark.asyncio
async def test_last_active_company_admin_guard_rejects_lockout() -> None:
    store = object.__new__(MemberStore)
    session = AsyncMock()
    session.scalar.return_value = None

    with pytest.raises(ApiError) as exc:
        await store._require_other_active_company_admin(
            session,
            scope=_scope(),
            exclude_membership_id=uuid.uuid4(),
        )

    assert exc.value.status_code == 409
    assert exc.value.code == "LAST_COMPANY_ADMIN_REQUIRED"
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_last_active_company_admin_guard_accepts_another_enabled_admin() -> None:
    store = object.__new__(MemberStore)
    session = AsyncMock()
    session.scalar.return_value = uuid.uuid4()

    await store._require_other_active_company_admin(
        session,
        scope=_scope(),
        exclude_membership_id=uuid.uuid4(),
    )

    session.scalar.assert_awaited_once()
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_last_admin_check_acquires_company_lock_before_counting_admins() -> None:
    events: list[str] = []

    class OrderedSession:
        async def execute(self, _statement: object, _parameters: object) -> None:
            events.append("lock")

        async def scalar(self, _statement: object) -> uuid.UUID:
            events.append("count")
            return uuid.uuid4()

    store = object.__new__(MemberStore)
    await store._require_other_active_company_admin(
        OrderedSession(),  # type: ignore[arg-type]
        scope=_scope(),
        exclude_membership_id=uuid.uuid4(),
    )

    assert events == ["lock", "count"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["status", "access", "bulk"])
async def test_every_admin_lockout_path_calls_the_shared_guard(operation: str) -> None:
    """Single disable, demotion, and bulk upsert share one serialized invariant."""

    store = object.__new__(MemberStore)
    store._sessions = None
    guard = AsyncMock(
        side_effect=ApiError(
            409,
            "LAST_COMPANY_ADMIN_REQUIRED",
            "At least one active company administrator must remain.",
        )
    )
    store._require_other_active_company_admin = guard
    scope = _scope()
    membership = SimpleNamespace(
        id=scope.actor_user_id,
        user_id=scope.actor_user_id,
        role=MembershipRole.COMPANY_ADMIN,
        permissions=["company.manage"],
        status=LifecycleStatus.ACTIVE,
    )
    credential = SimpleNamespace(
        is_enabled=True,
        failed_attempts=0,
        locked_until=None,
        last_failed_at=None,
    )
    session = AsyncMock()

    with pytest.raises(ApiError) as exc:
        desired_role = (
            MembershipRole.CARD_OWNER
            if operation in {"access", "bulk"}
            else MembershipRole.COMPANY_ADMIN
        )
        desired_status = (
            LifecycleStatus.DISABLED if operation == "status" else LifecycleStatus.ACTIVE
        )
        await store._guard_admin_transition(
            session,
            scope=scope,
            membership=membership,
            credential=credential,
            desired_role=desired_role,
            desired_status=desired_status,
        )

    assert exc.value.code == "LAST_COMPANY_ADMIN_REQUIRED"
    guard.assert_awaited_once_with(
        session,
        scope=scope,
        exclude_membership_id=membership.id,
    )
