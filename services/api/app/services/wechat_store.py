from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.core.staff_auth import hash_staff_password
from app.integrations.wechat import WeChatIdentity


@dataclass(frozen=True, slots=True)
class WeChatAccount:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    account_hash: str


class WeChatStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self._sessions = sessions
        self._cipher = PiiCipher.from_settings(settings)

    async def provision(self, identity: WeChatIdentity) -> WeChatAccount:
        # AppID is part of the identity: OpenIDs from different accounts must
        # never collide, and optional UnionID is not an automatic account merge.
        account_hash = self._cipher.hmac(f"wechat:{identity.app_id}:{identity.open_id}")
        async with self._sessions() as session, session.begin():
            try:
                result = await session.execute(
                    text("""
                    SELECT user_id, membership_id, tenant_id, company_id
                    FROM app.provision_wechat_account(
                        :identity_hash, :identity_ciphertext, :key_ref, :password_hash
                    )
                """),
                    {
                        "identity_hash": account_hash,
                        "identity_ciphertext": self._cipher.encrypt(identity.open_id),
                        "key_ref": self._cipher.key_ref,
                        "password_hash": hash_staff_password(secrets.token_urlsafe(48)),
                    },
                )
            except DBAPIError as exc:
                if getattr(exc.orig, "sqlstate", None) == "P0001":
                    raise ApiError(
                        403, "WECHAT_ACCOUNT_DISABLED", "账号已停用，请联系平台客服"
                    ) from None
                raise
            row = result.mappings().one()
        return WeChatAccount(**dict(row), account_hash=account_hash)
