from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.catalog_schemas import UpdateManagedCardRequest
from app.api.errors import ApiError
from app.api.member_schemas import UpdateSelfProfileRequest
from app.core.config import Settings
from app.integrations.wechat import WeChatIdentity
from app.services.auth_store import AuthStore
from app.services.catalog_store import CatalogScope, CatalogStore
from app.services.member_store import MemberScope, MemberStore
from app.services.public_store import PublicStore
from app.services.wechat_store import WeChatStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_WECHAT_INTEGRATION") != "1",
        reason="requires a disposable migrated database and RUN_WECHAT_INTEGRATION=1",
    ),
]


@pytest.mark.asyncio
async def test_personal_workspace_concurrency_publish_and_cross_tenant_isolation():
    settings = Settings()
    admin = create_async_engine(settings.database_url)
    runtime = create_async_engine(make_url(settings.database_url).set(username="cf_ai_card_app"))
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    store = WeChatStore(sessions, settings)
    identity = WeChatIdentity(app_id="wx-first", open_id=uuid.uuid4().hex)
    try:
        first, repeated = await asyncio.gather(store.provision(identity), store.provision(identity))
        assert first == repeated
        other = await store.provision(WeChatIdentity(app_id="wx-second", open_id=identity.open_id))
        assert other.tenant_id != first.tenant_id and other.user_id != first.user_id
        authentication = await AuthStore(sessions, settings).authenticate_trusted_identity(
            user_id=first.user_id,
            membership_id=first.membership_id,
            tenant_id=first.tenant_id,
            company_id=first.company_id,
            account_hash=first.account_hash,
            event_type="staff.wechat_login",
        )
        assert authentication.identity.role == "card_owner"
        assert not authentication.identity.must_change_password
        assert "company.manage" not in authentication.identity.permissions
        catalog = CatalogStore(sessions, public_card_base_url="https://cards.example")
        scope = CatalogScope(first.tenant_id, first.company_id, first.user_id, "card_owner")
        cards, count = await catalog.list_cards(scope=scope, limit=20, offset=0)
        assert count == 1 and cards[0].status == "draft"
        card = cards[0]
        with pytest.raises(ApiError):
            await PublicStore(sessions, settings).get_public_card(slug=card.slug)
        # The self-profile API accepts the URL produced by the scoped upload API.
        avatar = f"/api/v1/public/card-assets/{first.company_id}/{uuid.uuid4()}.webp"
        await MemberStore(sessions, settings).update_self_profile(
            scope=MemberScope(
                first.tenant_id,
                first.company_id,
                first.user_id,
                uuid.uuid4(),
                actor_role="card_owner",
            ),
            membership_id=first.membership_id,
            body=UpdateSelfProfileRequest(avatar_url=avatar),
            trace_id=None,
        )
        updated = await catalog.update_card(
            scope=scope,
            card_id=card.id,
            expected_version=card.version,
            body=UpdateManagedCardRequest(
                card_kind="employee",
                owner_user_id=first.user_id,
                display_name="微信名片主人",
                title="产品设计师",
            ),
        )
        published = await catalog.publish_card(
            scope=scope, card_id=card.id, expected_version=updated.version
        )
        assert published.status == "published"
        public = await PublicStore(sessions, settings).get_public_card(slug=card.slug)
        assert public.display_name == "微信名片主人"
        assert public.avatar_url == avatar
        other_scope = CatalogScope(other.tenant_id, other.company_id, other.user_id, "card_owner")
        with pytest.raises(ApiError):
            await catalog.get_card(scope=other_scope, card_id=card.id)
        async with runtime.begin() as connection:
            with pytest.raises(DBAPIError):
                await connection.execute(text("SELECT * FROM wechat_accounts"))
        async with admin.begin() as connection:
            await connection.execute(
                text("UPDATE memberships SET status='disabled' WHERE id=:id"),
                {"id": first.membership_id},
            )
        with pytest.raises(ApiError, match="WECHAT_ACCOUNT_DISABLED"):
            await store.provision(identity)
    finally:
        await runtime.dispose()
        await admin.dispose()
