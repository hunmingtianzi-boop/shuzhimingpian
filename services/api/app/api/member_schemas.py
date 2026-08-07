from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.api.catalog_schemas import validate_safe_asset_url
from app.core.staff_auth import normalize_staff_account

MemberRole = Literal["company_admin", "card_owner"]
MemberStatus = Literal["active", "disabled"]
MemberLifecycleStatus = Literal["active", "suspended", "disabled"]
MemberRowOutcome = Literal["created", "updated", "unchanged", "duplicate", "failed"]

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_MOBILE_PATTERN = re.compile(r"^\+?[0-9]{6,20}$")
_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9_.:-]{0,79}$")
ALLOWED_COMPANY_MEMBER_PERMISSIONS = frozenset(
    {
        "analytics.read",
        "card.manage",
        "card.read",
        "card.write",
        "case_study.publish",
        "case_study.read",
        "case_study.write",
        "catalog.manage",
        "catalog.publish",
        "catalog.read",
        "catalog.write",
        "company.manage",
        "company.profile.read",
        "company.profile.write",
        "conversations.read",
        "forbidden_topic.manage",
        "forbidden_topic.read",
        "forbidden_topic.write",
        "knowledge.manage",
        "knowledge.publish",
        "knowledge.read",
        "knowledge.review",
        "knowledge.write",
        "leads.read",
        "leads.write",
        "members.manage",
        "members.write",
        "privacy.manage",
        "product.publish",
        "product.read",
        "product.write",
        "summaries.read",
        "summaries.write",
        "visits.read",
    }
)


class MemberModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BulkMemberRow(MemberModel):
    account: str = Field(min_length=3, max_length=200)
    display_name: str = Field(min_length=1, max_length=120)
    password: SecretStr
    email: str | None = Field(default=None, max_length=320)
    mobile: str | None = Field(default=None, max_length=24)
    job_title: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2_048)
    business_summary: str | None = Field(default=None, max_length=2_000)
    role: MemberRole = "card_owner"
    permissions: list[str] | None = Field(default=None, max_length=40)
    status: MemberStatus = "active"
    rotate_password: bool = False

    _validate_avatar_url = field_validator("avatar_url")(validate_safe_asset_url)

    @field_validator("account")
    @classmethod
    def validate_account(cls, value: str) -> str:
        return normalize_staff_account(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        length = len(value.get_secret_value())
        if not 12 <= length <= 200:
            raise ValueError("password must contain 12-200 characters")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.casefold()
        if len(normalized) > 254 or _EMAIL_PATTERN.fullmatch(normalized) is None:
            raise ValueError("email format is invalid")
        return normalized

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace(" ", "").replace("-", "")
        if _MOBILE_PATTERN.fullmatch(normalized) is None:
            raise ValueError("mobile format is invalid")
        return normalized

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        for permission in value:
            candidate = permission.strip().casefold()
            if (
                _PERMISSION_PATTERN.fullmatch(candidate) is None
                or candidate not in ALLOWED_COMPANY_MEMBER_PERMISSIONS
            ):
                raise ValueError("permission format is invalid")
            if candidate not in normalized:
                normalized.append(candidate)
        return sorted(normalized)

    @model_validator(mode="after")
    def infer_email_from_account(self) -> BulkMemberRow:
        if self.email is None and "@" in self.account:
            if _EMAIL_PATTERN.fullmatch(self.account) is None:
                raise ValueError("email account format is invalid")
            self.email = self.account
        return self


class CreateMemberRequest(BulkMemberRow):
    pass


class BulkMemberRequest(MemberModel):
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class BulkMemberCsvRequest(MemberModel):
    csv_text: str = Field(min_length=1, max_length=1_000_000)


class MemberRecord(MemberModel):
    membership_id: uuid.UUID
    user_id: uuid.UUID
    account: str
    display_name: str
    job_title: str | None = None
    avatar_url: str | None = None
    business_summary: str | None = None
    role: MemberRole
    permissions: list[str]
    status: MemberLifecycleStatus
    credential_enabled: bool
    created_at: datetime
    updated_at: datetime


class MemberRowError(MemberModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)
    fields: list[str] = Field(default_factory=list)


class BulkMemberRowResult(MemberModel):
    row_number: int = Field(ge=1)
    account: str | None = None
    outcome: MemberRowOutcome
    member: MemberRecord | None = None
    error: MemberRowError | None = None
    duplicate_of_row: int | None = Field(default=None, ge=1)


class BulkMemberSummary(MemberModel):
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    created: int = Field(ge=0)
    updated: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    duplicated: int = Field(ge=0)
    failed: int = Field(ge=0)


class BulkMemberResult(MemberModel):
    batch_id: uuid.UUID
    summary: BulkMemberSummary
    rows: list[BulkMemberRowResult]


class BulkMemberEnvelope(MemberModel):
    data: BulkMemberResult


class MemberListEnvelope(MemberModel):
    data: list[MemberRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class UpdateMemberStatusRequest(MemberModel):
    status: MemberStatus


class MemberEnvelope(MemberModel):
    data: MemberRecord


class UpdateMemberAccessRequest(MemberModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    job_title: str | None = Field(default=None, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2_048)
    business_summary: str | None = Field(default=None, max_length=2_000)
    role: MemberRole | None = None
    permissions: list[str] | None = Field(default=None, max_length=40)

    _validate_avatar_url = field_validator("avatar_url")(validate_safe_asset_url)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, value: list[str] | None) -> list[str] | None:
        return BulkMemberRow.validate_permissions(value)

    @model_validator(mode="after")
    def require_change(self) -> UpdateMemberAccessRequest:
        if not self.model_fields_set:
            raise ValueError("at least one member field must be supplied")
        return self


class UpdateSelfProfileRequest(MemberModel):
    """Narrow self-service surface; target identity always comes from the token."""

    avatar_url: str | None = Field(max_length=2_048)

    _validate_avatar_url = field_validator("avatar_url")(validate_safe_asset_url)


class ResetMemberPasswordRequest(MemberModel):
    password: SecretStr
    revoke_sessions: Literal[True] = True

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        return BulkMemberRow.validate_password(value)


class PasswordResetRecord(MemberModel):
    membership_id: uuid.UUID
    password_changed_at: datetime
    sessions_revoked: int = Field(ge=0)


class PasswordResetEnvelope(MemberModel):
    data: PasswordResetRecord


__all__ = [
    "BulkMemberEnvelope",
    "BulkMemberCsvRequest",
    "BulkMemberRequest",
    "BulkMemberResult",
    "BulkMemberRow",
    "BulkMemberRowResult",
    "BulkMemberSummary",
    "CreateMemberRequest",
    "MemberEnvelope",
    "MemberListEnvelope",
    "MemberRecord",
    "MemberRowError",
    "MemberStatus",
    "PasswordResetEnvelope",
    "PasswordResetRecord",
    "ResetMemberPasswordRequest",
    "UpdateMemberAccessRequest",
    "UpdateSelfProfileRequest",
    "UpdateMemberStatusRequest",
    "ALLOWED_COMPANY_MEMBER_PERMISSIONS",
]
