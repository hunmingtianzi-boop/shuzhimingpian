from __future__ import annotations

import os
import uuid
from dataclasses import replace

import pytest
from sqlalchemy import delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.errors import ApiError
from app.api.member_schemas import UpdateMemberAccessRequest
from app.core.config import Settings
from app.core.tokens import decode_staff_access_token
from app.db.models import StaffCredential
from app.integrations.wecom import WeComMember
from app.services.auth_store import AuthStore
from app.services.member_store import MemberScope, MemberStore
from app.services.wecom_store import WeComStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_MEMBER_DIRECTORY_INTEGRATION") != "1",
        reason="requires disposable migrated test database",
    ),
]


@pytest.mark.asyncio
async def test_oauth_directory_permissions_and_company_isolation() -> None:
    settings = Settings()
    assert "test" in (make_url(settings.database_url).database or "")
    runtime = create_async_engine(settings.database_url)
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False, autoflush=False)
    wecom = WeComStore(sessions, settings)
    auth = AuthStore(sessions, settings)
    directory = MemberStore(sessions, settings)
    member = WeComMember(
        user_id="admin",
        name="Directory Admin",
        departments=(),
        position=None,
        avatar_url=None,
        status=1,
    )
    corp = f"ww-directory-{uuid.uuid4().hex}"

    async def join(corp_id, user_id, name, bootstrap=False):
        return await wecom.resolve_or_bootstrap_identity(
            member=replace(member, user_id=user_id, name=name),
            enterprise_name="Directory Test",
            corp_id=corp_id,
            allow_bootstrap=bootstrap,
        )

    async def login(identity):
        result = await auth.authenticate_trusted_identity(
            user_id=identity.user_id,
            membership_id=identity.membership_id,
            tenant_id=identity.tenant_id,
            company_id=identity.company_id,
            account_hash=identity.account_hash,
            event_type="staff.wecom_login",
        )
        return decode_staff_access_token(
            result.tokens.access_token,
            signing_key=settings.jwt_signing_key.get_secret_value(),
            issuer=settings.app_name,
        )

    try:
        first = await join(corp, "admin", "Directory Admin", True)
        employee = await join(corp, "employee", "Joined Employee")
        dormant = await join(corp, "dormant", "No Login")
        other = await join(corp + "-other", "admin", "Other Company", True)
        admin_principal = await login(first)
        employee_principal = await login(employee)
        scope = MemberScope(
            tenant_id=first.tenant_id,
            company_id=first.company_id,
            actor_user_id=first.user_id,
            actor_session_id=admin_principal.session_id,
        )
        # Exercise the historical OAuth-only ordinary-member shape too.
        async with owner.begin() as connection:
            assert "test" in await connection.scalar(text("select current_database()"))
            await connection.execute(
                delete(StaffCredential).where(
                    StaffCredential.membership_id == employee.membership_id
                )
            )
        items, total, summary = await directory.list_members(scope=scope, limit=1, offset=0)
        assert total == summary.total == 3 and len(items) == 1
        assert summary.logged_in == summary.active_last_7_days == 2
        assert summary.administrators == 1
        items, total, filtered_summary = await directory.list_members(
            scope=scope,
            limit=50,
            offset=0,
            role="card_owner",
            login_status="logged_in",
            query="Joined",
        )
        assert total == 1 and items[0].membership_id == employee.membership_id
        assert items[0].account is None and not items[0].has_password_account
        assert items[0].wecom_connected and items[0].last_login_at
        assert filtered_summary == summary
        items, total, _ = await directory.list_members(
            scope=scope, limit=50, offset=0, login_status="not_logged_in"
        )
        assert total == 1 and items[0].membership_id == dormant.membership_id
        assert (await directory.list_members(scope=scope, limit=50, offset=0, query="%"))[1] == 0
        with pytest.raises(ApiError) as cross_scope:
            await directory.update_access(
                scope=scope,
                membership_id=other.membership_id,
                body=UpdateMemberAccessRequest(role="company_admin"),
                trace_id=None,
            )
        assert cross_scope.value.code == "MEMBER_NOT_FOUND"
        with pytest.raises(ApiError) as last_admin:
            await directory.update_access(
                scope=scope,
                membership_id=first.membership_id,
                body=UpdateMemberAccessRequest(role="card_owner"),
                trace_id=None,
            )
        assert last_admin.value.code == "LAST_COMPANY_ADMIN_REQUIRED"
        promoted = await directory.update_access(
            scope=scope,
            membership_id=employee.membership_id,
            body=UpdateMemberAccessRequest(role="company_admin"),
            trace_id=None,
        )
        assert promoted.role == "company_admin" and promoted.account is None
        assert (await auth.get_current(employee_principal)).role == "company_admin"
        # An OAuth-only second administrator makes a downgrade safe.
        changed = await directory.update_access(
            scope=scope,
            membership_id=first.membership_id,
            body=UpdateMemberAccessRequest(role="card_owner", permissions=["card.read"]),
            trace_id=None,
        )
        assert changed.role == "card_owner"
        new_scope = replace(
            scope, actor_user_id=employee.user_id, actor_session_id=employee_principal.session_id
        )
        with pytest.raises(ApiError) as remaining:
            await directory.set_status(
                scope=new_scope,
                membership_id=employee.membership_id,
                status="disabled",
                trace_id=None,
            )
        assert remaining.value.code == "LAST_COMPANY_ADMIN_REQUIRED"
        disabled = await directory.set_status(
            scope=new_scope, membership_id=first.membership_id, status="disabled", trace_id=None
        )
        assert disabled.status == "disabled"
        with pytest.raises(ApiError):
            await auth.get_current(admin_principal)
        delegated = replace(
            new_scope, actor_role="card_owner", actor_permissions=("members.manage", "card.read")
        )
        with pytest.raises(ApiError) as forbidden:
            await directory.update_access(
                scope=delegated,
                membership_id=dormant.membership_id,
                body=UpdateMemberAccessRequest(role="company_admin"),
                trace_id=None,
            )
        assert forbidden.value.status_code == 403
    finally:
        await runtime.dispose()
        await owner.dispose()
