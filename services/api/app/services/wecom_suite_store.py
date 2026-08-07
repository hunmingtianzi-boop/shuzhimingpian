from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.integrations.wecom_suite import WeComSuiteAuthorizationGrant


@dataclass(frozen=True, slots=True)
class WeComStoredAuthorization:
    id: uuid.UUID
    auth_corpid: str
    permanent_code: str
    corp_name: str
    agent_id: int | None
    authorizer_user_id: str | None


class WeComSuiteStore:
    """Encrypted persistence facade for global provider authorizations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._cipher = PiiCipher.from_settings(settings)

    async def save_authorization(
        self, grant: WeComSuiteAuthorizationGrant
    ) -> WeComStoredAuthorization:
        metadata = json.dumps(
            grant.metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        async with self._sessions() as session, session.begin():
            authorization_id = await session.scalar(
                text(
                    """
                    SELECT app.upsert_wecom_enterprise_authorization(
                      :suite_hash,
                      :corp_hash,
                      :corp_ciphertext,
                      :permanent_code_ciphertext,
                      :authorization_ciphertext,
                      :authorizer_ciphertext,
                      :key_ref,
                      :agent_id
                    )
                    """
                ),
                {
                    "suite_hash": self.suite_hash(),
                    "corp_hash": self.corp_hash(grant.auth_corpid),
                    "corp_ciphertext": self._cipher.encrypt(grant.auth_corpid),
                    "permanent_code_ciphertext": self._cipher.encrypt(
                        grant.permanent_code
                    ),
                    "authorization_ciphertext": self._cipher.encrypt(metadata),
                    "authorizer_ciphertext": (
                        self._cipher.encrypt(grant.authorizer_user_id)
                        if grant.authorizer_user_id
                        else None
                    ),
                    "key_ref": self._cipher.key_ref,
                    "agent_id": grant.agent_id,
                },
            )
        if not isinstance(authorization_id, uuid.UUID):
            raise RuntimeError("WeCom authorization upsert returned no identifier")
        return WeComStoredAuthorization(
            id=authorization_id,
            auth_corpid=grant.auth_corpid,
            permanent_code=grant.permanent_code,
            corp_name=grant.corp_name,
            agent_id=grant.agent_id,
            authorizer_user_id=grant.authorizer_user_id,
        )

    async def get_authorization(self, *, auth_corpid: str) -> WeComStoredAuthorization:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                text(
                    """
                    SELECT authorization_id,
                           auth_corpid_ciphertext,
                           permanent_code_ciphertext,
                           authorization_ciphertext,
                           authorizer_user_id_ciphertext,
                           encryption_key_ref,
                           agent_id
                    FROM app.get_wecom_enterprise_authorization(
                      :suite_hash,
                      :corp_hash
                    )
                    """
                ),
                {
                    "suite_hash": self.suite_hash(),
                    "corp_hash": self.corp_hash(auth_corpid),
                },
            )
            row = result.mappings().one_or_none()
        if row is None:
            raise ApiError(
                403,
                "WECOM_ENTERPRISE_NOT_AUTHORIZED",
                "该企业尚未授权安装数智名片应用",
            )
        stored_corp_id = self._cipher.decrypt(row["auth_corpid_ciphertext"])
        if stored_corp_id != auth_corpid:
            raise ApiError(403, "WECOM_ENTERPRISE_NOT_AUTHORIZED", "企业授权校验失败")
        metadata_raw = self._cipher.decrypt(row["authorization_ciphertext"])
        try:
            metadata = json.loads(metadata_raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("WeCom authorization metadata is invalid") from exc
        corp_info = metadata.get("auth_corp_info") if isinstance(metadata, dict) else None
        corp_name = corp_info.get("corp_name") if isinstance(corp_info, dict) else None
        return WeComStoredAuthorization(
            id=row["authorization_id"],
            auth_corpid=stored_corp_id,
            permanent_code=self._cipher.decrypt(row["permanent_code_ciphertext"]),
            corp_name=(
                corp_name[:200]
                if isinstance(corp_name, str) and corp_name
                else "企业微信企业"
            ),
            agent_id=row["agent_id"] if isinstance(row["agent_id"], int) else None,
            authorizer_user_id=(
                self._cipher.decrypt(row["authorizer_user_id_ciphertext"])
                if row["authorizer_user_id_ciphertext"] is not None
                else None
            ),
        )

    async def revoke_authorization(self, *, auth_corpid: str) -> bool:
        async with self._sessions() as session, session.begin():
            revoked = await session.scalar(
                text(
                    """
                    SELECT app.revoke_wecom_enterprise_authorization(
                      :suite_hash,
                      :corp_hash
                    )
                    """
                ),
                {
                    "suite_hash": self.suite_hash(),
                    "corp_hash": self.corp_hash(auth_corpid),
                },
            )
        return bool(revoked)

    async def require_scope(
        self,
        *,
        auth_corpid: str,
        tenant_id: uuid.UUID,
        company_id: uuid.UUID,
    ) -> None:
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                text(
                    """
                    SELECT tenant_id, company_id
                    FROM app.resolve_wecom_enterprise_scope(:corp_hash)
                    """
                ),
                {"corp_hash": self.corp_hash(auth_corpid)},
            )
            row = result.mappings().one_or_none()
        if (
            row is None
            or row["tenant_id"] != tenant_id
            or row["company_id"] != company_id
        ):
            raise ApiError(403, "WECOM_ENTERPRISE_SCOPE_MISMATCH", "企业微信企业与后台不匹配")

    def suite_hash(self) -> str:
        suite_id = self._settings.wecom_suite_id
        if not suite_id:
            raise ApiError(409, "WECOM_SUITE_NOT_CONFIGURED", "企微服务商应用尚未配置")
        return self._cipher.hmac(f"wecom-suite:{suite_id}")

    def corp_hash(self, corp_id: str) -> str:
        return self._cipher.hmac(f"wecom-corp:{corp_id}")


__all__ = ["WeComStoredAuthorization", "WeComSuiteStore"]
