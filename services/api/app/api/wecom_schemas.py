from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WeComModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class WeComIntegrationStatus(WeComModel):
    configured: bool
    reachable: bool | None = None
    callback_configured: bool
    oauth_configured: bool
    identity_scope_configured: bool
    corp_id_hint: str | None = None
    agent_id: int | None = None
    agent_name: str | None = None
    error_code: str | None = None


class WeComIntegrationStatusEnvelope(WeComModel):
    data: WeComIntegrationStatus


class WeComTestMessageRequest(WeComModel):
    user_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.@-]+$")
    content: str = Field(
        default="创非凡数智名片：企业微信试验连接成功。",
        min_length=1,
        max_length=1000,
    )


class WeComTestMessageRecord(WeComModel):
    delivered: bool
    message_id: str | None = None


class WeComTestMessageEnvelope(WeComModel):
    data: WeComTestMessageRecord


class WeComDepartmentRecord(WeComModel):
    id: int = Field(ge=1)
    name: str
    parent_id: int | None = None
    order: int | None = None


class WeComDepartmentList(WeComModel):
    items: tuple[WeComDepartmentRecord, ...]


class WeComDepartmentListEnvelope(WeComModel):
    data: WeComDepartmentList


class WeComOAuthUrl(WeComModel):
    authorize_url: str
    expires_in: int = Field(ge=120, le=1_800)


class WeComOAuthUrlEnvelope(WeComModel):
    data: WeComOAuthUrl


class WeComOAuthExchangeRequest(WeComModel):
    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=20, max_length=4_096)


class WeComBindingRecord(WeComModel):
    id: uuid.UUID
    membership_id: uuid.UUID
    member_name: str | None = None
    bound: bool = True


class WeComBindingEnvelope(WeComModel):
    data: WeComBindingRecord


class WeComCardContactWayRecord(WeComModel):
    id: uuid.UUID
    card_id: uuid.UUID
    owner_user_id: uuid.UUID
    qr_code_url: str | None = None
    provisioned_at: datetime


class WeComCardContactWayEnvelope(WeComModel):
    data: WeComCardContactWayRecord | None


__all__ = [
    "WeComIntegrationStatus",
    "WeComIntegrationStatusEnvelope",
    "WeComBindingEnvelope",
    "WeComBindingRecord",
    "WeComCardContactWayEnvelope",
    "WeComCardContactWayRecord",
    "WeComDepartmentList",
    "WeComDepartmentListEnvelope",
    "WeComDepartmentRecord",
    "WeComOAuthExchangeRequest",
    "WeComOAuthUrl",
    "WeComOAuthUrlEnvelope",
    "WeComTestMessageEnvelope",
    "WeComTestMessageRecord",
    "WeComTestMessageRequest",
]
