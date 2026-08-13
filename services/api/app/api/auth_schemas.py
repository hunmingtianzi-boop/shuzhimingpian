from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictAuthModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginRequest(StrictAuthModel):
    account: str = Field(min_length=3, max_length=200)
    credential: str = Field(min_length=1, max_length=200)
    method: Literal["password"] = "password"


class StaffTokenData(StrictAuthModel):
    access_token: str
    csrf_token: str = Field(min_length=32, max_length=256)
    token_type: Literal["Bearer"] = "Bearer"  # noqa: S105 - OAuth token scheme
    expires_in: int = Field(ge=60)
    refresh_expires_in: int = Field(ge=3_600)


class AuthEnvelope(StrictAuthModel):
    data: StaffTokenData


class StaffUserView(StrictAuthModel):
    id: uuid.UUID
    display_name: str


class StaffMembershipView(StrictAuthModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    role: str
    permissions: tuple[str, ...]


class CurrentStaffData(StrictAuthModel):
    user: StaffUserView
    membership: StaffMembershipView
    must_change_password: bool = False


class ChangePasswordRequest(StrictAuthModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


class ChangePasswordData(StrictAuthModel):
    changed: bool = True


class ChangePasswordEnvelope(StrictAuthModel):
    data: ChangePasswordData


class CurrentStaffEnvelope(StrictAuthModel):
    data: CurrentStaffData


class LogoutData(StrictAuthModel):
    revoked: Literal[True] = True


class LogoutEnvelope(StrictAuthModel):
    data: LogoutData
