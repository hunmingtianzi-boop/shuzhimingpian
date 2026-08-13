from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    Float,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    CompanyScopeMixin,
    OptimisticVersionMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)

EMBEDDING_DIMENSION = 1024


def db_enum(enum_type: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


class TenantType(StrEnum):
    CHAMBER = "chamber"
    ENTERPRISE = "enterprise"


class LifecycleStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class ContentStatus(StrEnum):
    DRAFT = "draft"
    REVIEW_PENDING = "review_pending"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CardKind(StrEnum):
    ENTERPRISE = "enterprise"
    EMPLOYEE = "employee"


class DistributedContentType(StrEnum):
    PRODUCT = "product"
    CASE_STUDY = "case_study"
    KNOWLEDGE_DOCUMENT = "knowledge_document"


class CardContentOverrideMode(StrEnum):
    INHERIT = "inherit"
    HIDDEN = "hidden"
    CUSTOM = "custom"


class LeadStatus(StrEnum):
    NEW = "new"
    VIEWED = "viewed"
    FOLLOWING = "following"
    WON = "won"
    LOST = "lost"
    INVALID = "invalid"


class PrivacyRequestType(StrEnum):
    ACCESS = "access"
    CORRECTION = "correction"
    DELETION = "deletion"
    WITHDRAW_CONSENT = "withdraw_consent"


class PrivacyRequestStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class MembershipRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    COMPANY_ADMIN = "company_admin"
    CARD_OWNER = "card_owner"


class Visibility(StrEnum):
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    INTERNAL = "internal"


class ConsentScope(StrEnum):
    BROWSE_NOTICE = "browse_notice"
    CHAT_NOTICE = "chat_notice"
    LEAD_CONTACT = "lead_contact"
    PROFILE_PERSONALIZATION = "profile_personalization"


class VisitorProfileSignalKind(StrEnum):
    INTEREST = "interest"
    INTENT = "intent"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    HUMAN = "human"


class MessageStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    REFUSED = "refused"
    FAILED = "failed"


class ReviewStatus(StrEnum):
    DRAFT = "draft"
    REVIEW_PENDING = "review_pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class IndexJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class KnowledgeGapStatus(StrEnum):
    PENDING = "pending"
    DRAFTED = "drafted"
    APPROVED = "approved"
    INDEXING = "indexing"
    INDEXED = "indexed"
    REJECTED = "rejected"
    FAILED = "failed"


class KnowledgeImportBatchStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class KnowledgeImportItemStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class PromptStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class IdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class ScheduledPublishResourceType(StrEnum):
    PRODUCT = "product"
    CASE_STUDY = "case_study"
    KNOWLEDGE_DOCUMENT = "knowledge_document"


class ScheduledPublishStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class DataExportType(StrEnum):
    VISITORS = "visitors"
    LEADS = "leads"
    CONVERSATIONS = "conversations"


class DataExportStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'",
            name="slug_format",
        ),
        UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tenant_type: Mapped[TenantType] = mapped_column(
        "type",
        db_enum(TenantType, "tenant_type"),
        nullable=False,
    )
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "tenant_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class Company(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticVersionMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "id", name="uq_companies_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "normalized_name",
            name="uq_companies_tenant_id_normalized_name",
        ),
        CheckConstraint("char_length(btrim(name)) > 0", name="name_not_blank"),
        Index("ix_companies_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "company_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class User(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, OptimisticVersionMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_email_hmac", "email_hmac", unique=True),
        Index("uq_users_mobile_hmac", "mobile_hmac", unique=True),
    )

    email_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mobile_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mobile_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "user_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )


class Membership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "user_id",
            "tenant_id",
            "company_id",
            name="uq_memberships_user_scope",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_memberships_scope_status", "tenant_id", "company_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    role: Mapped[MembershipRole] = mapped_column(
        db_enum(MembershipRole, "membership_role"),
        nullable=False,
    )
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(String(80)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    business_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LifecycleStatus] = mapped_column(
        db_enum(LifecycleStatus, "membership_status"),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
        server_default=text("'active'"),
    )


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("refresh_token_hash", name="uq_auth_sessions_refresh_token_hash"),
        Index("ix_auth_sessions_user_expires", "user_id", "expires_at"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)


class WeComUserBinding(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    """Encrypted mapping between an internal membership and a WeCom member."""

    __tablename__ = "wecom_user_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["membership_id"], ["memberships.id"], ondelete="CASCADE"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "membership_id",
            name="uq_wecom_user_bindings_membership",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "corp_id_hmac",
            "wecom_user_id_hmac",
            name="uq_wecom_user_bindings_provider_user",
        ),
        CheckConstraint("char_length(corp_id_hmac) = 64", name="corp_id_hmac_sha256"),
        CheckConstraint(
            "char_length(wecom_user_id_hmac) = 64",
            name="wecom_user_id_hmac_sha256",
        ),
        Index(
            "ix_wecom_user_bindings_company_active",
            "company_id",
            "revoked_at",
            "updated_at",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    corp_id_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    wecom_user_id_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wecom_user_id_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encryption_key_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WeComEnterpriseScope(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Global, non-PII mapping from one WeCom corporation to its tenant scope.

    Runtime access is intentionally limited to the security-definer functions
    installed by the matching migration.  The application role receives no
    direct table privileges, preventing arbitrary cross-tenant discovery.
    """

    __tablename__ = "wecom_enterprise_scopes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["provisioned_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("corp_id_hmac", name="uq_wecom_enterprise_scopes_corp"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            name="uq_wecom_enterprise_scopes_scope",
        ),
        CheckConstraint("char_length(corp_id_hmac) = 64", name="corp_id_hmac_sha256"),
    )

    corp_id_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    provisioned_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )


class WeComEnterpriseAuthorization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Encrypted third-party authorization for one customer corporation.

    This global provider index is accessed only through the narrow
    SECURITY DEFINER functions installed by its migration.
    """

    __tablename__ = "wecom_enterprise_authorizations"
    __table_args__ = (
        UniqueConstraint(
            "suite_id_hmac",
            "auth_corpid_hmac",
            name="uq_wecom_enterprise_authorizations_provider_corp",
        ),
        CheckConstraint("char_length(suite_id_hmac) = 64", name="suite_id_hmac_sha256"),
        CheckConstraint(
            "char_length(auth_corpid_hmac) = 64",
            name="auth_corpid_hmac_sha256",
        ),
        CheckConstraint(
            "status IN ('active', 'revoked')",
            name="authorization_status_allowed",
        ),
        Index(
            "ix_wecom_enterprise_authorizations_status",
            "suite_id_hmac",
            "status",
            "updated_at",
        ),
    )

    suite_id_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    auth_corpid_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    auth_corpid_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    permanent_code_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    authorization_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    authorizer_user_id_ciphertext: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    encryption_key_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="active", server_default=text("'active'")
    )
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WeComCallbackEvent(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    """Verified WeCom callback retained encrypted for idempotent processing."""

    __tablename__ = "wecom_callback_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "provider_event_key",
            name="uq_wecom_callback_events_provider_key",
        ),
        CheckConstraint("char_length(corp_id_hmac) = 64", name="corp_id_hmac_sha256"),
        CheckConstraint(
            "char_length(provider_event_key) = 64",
            name="provider_event_key_sha256",
        ),
        CheckConstraint(
            "status IN ('received', 'processed', 'failed')",
            name="status_allowed",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        Index(
            "ix_wecom_callback_events_processing",
            "company_id",
            "status",
            "received_at",
        ),
    )

    corp_id_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    change_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="received", server_default=text("'received'")
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WeComCardContactWay(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    """A card-scoped WeCom customer-contact QR code with opaque attribution."""

    __tablename__ = "wecom_card_contact_ways"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["binding_id"], ["wecom_user_bindings.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "state_token_hmac",
            name="uq_wecom_card_contact_ways_state",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "config_id_hmac",
            name="uq_wecom_card_contact_ways_config",
        ),
        CheckConstraint(
            "char_length(state_token_hmac) = 64",
            name="wecom_card_contact_state_hmac_sha256",
        ),
        CheckConstraint(
            "char_length(config_id_hmac) = 64",
            name="wecom_card_contact_config_hmac_sha256",
        ),
        Index(
            "uq_wecom_card_contact_ways_active_card",
            "tenant_id",
            "company_id",
            "card_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "ix_wecom_card_contact_ways_owner_active",
            "owner_user_id",
            "revoked_at",
            "updated_at",
        ),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    binding_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    state_token_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    config_id_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    config_id_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    qr_code_url_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encryption_key_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    provisioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WeComCustomerLink(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    """Idempotent attribution from an external WeCom customer to one card owner."""

    __tablename__ = "wecom_customer_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "lead_id"],
            ["leads.tenant_id", "leads.company_id", "leads.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["contact_way_id"], ["wecom_card_contact_ways.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(
            ["binding_id"], ["wecom_user_bindings.id"], ondelete="CASCADE"
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "binding_id",
            "external_user_id_hmac",
            name="uq_wecom_customer_links_owner_external",
        ),
        CheckConstraint(
            "char_length(external_user_id_hmac) = 64",
            name="wecom_customer_external_hmac_sha256",
        ),
        Index(
            "ix_wecom_customer_links_card_created",
            "card_id",
            "created_at",
        ),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    contact_way_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    binding_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    owner_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    external_user_id_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    external_user_id_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    lead_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    encryption_key_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class StaffCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Unscoped login index; all post-password reads must switch into its scope."""

    __tablename__ = "staff_credentials"
    __table_args__ = (
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["membership_id"], ["memberships.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("account_normalized", name="uq_staff_credentials_account"),
        UniqueConstraint("membership_id", name="uq_staff_credentials_membership"),
        CheckConstraint(
            "account_normalized = lower(btrim(account_normalized)) "
            "AND char_length(account_normalized) BETWEEN 3 AND 200",
            name="account_normalized",
        ),
        CheckConstraint("failed_attempts >= 0", name="failed_attempts_non_negative"),
        Index("ix_staff_credentials_scope", "tenant_id", "company_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    account_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    failed_attempts: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_authenticated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    temporary_password_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Card(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "cards"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["responsible_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        UniqueConstraint("slug", name="uq_cards_slug"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_cards_scope_id"),
        CheckConstraint("slug = btrim(slug)", name="slug_trimmed"),
        CheckConstraint(
            "slug ~ '^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$'",
            name="slug_public_format",
        ),
        CheckConstraint(
            "(card_kind = 'enterprise' AND owner_user_id IS NULL) OR "
            "(card_kind = 'employee' AND owner_user_id IS NOT NULL "
            "AND responsible_user_id = owner_user_id)",
            name="kind_owner_consistent",
        ),
        Index("ix_cards_company_status_updated", "company_id", "status", "updated_at"),
        Index(
            "ix_cards_company_kind_status_updated",
            "company_id",
            "card_kind",
            "status",
            "updated_at",
        ),
        Index(
            "ix_cards_public_slug",
            "slug",
            postgresql_where=text("status = 'published' AND deleted_at IS NULL"),
        ),
    )

    card_kind: Mapped[CardKind] = mapped_column(
        db_enum(CardKind, "card_kind"),
        nullable=False,
        default=CardKind.EMPLOYEE,
        server_default=text("'employee'"),
    )
    owner_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    responsible_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        db_enum(ContentStatus, "card_status"),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=text("'draft'"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class CardContactField(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "card_contact_fields"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "card_id",
            "field_type",
            name="uq_card_contact_fields_card_type",
        ),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        Index("ix_card_contact_fields_card_order", "card_id", "sort_order", "id"),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    field_type: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    value_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    value_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    visibility: Mapped[Visibility] = mapped_column(
        db_enum(Visibility, "card_contact_visibility"),
        nullable=False,
        default=Visibility.PUBLIC,
        server_default=text("'public'"),
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    encryption_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class Product(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "products"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_products_scope_id"),
        UniqueConstraint("company_id", "slug", name="uq_products_company_slug"),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_requires_timestamp",
        ),
        Index("ix_products_company_status_updated", "company_id", "status", "updated_at"),
        Index("ix_products_company_category_order", "company_id", "category", "sort_order"),
    )

    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_boundary: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    visibility: Mapped[Visibility] = mapped_column(
        db_enum(Visibility, "product_visibility"),
        nullable=False,
        default=Visibility.PUBLIC,
        server_default=text("'public'"),
    )
    status: Mapped[ContentStatus] = mapped_column(
        db_enum(ContentStatus, "product_status"),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=text("'draft'"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class CaseStudy(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    SoftDeleteMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "case_studies"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_case_studies_scope_id"),
        UniqueConstraint("company_id", "slug", name="uq_case_studies_company_slug"),
        CheckConstraint("sort_order >= 0", name="sort_order_non_negative"),
        CheckConstraint(
            "status <> 'published' OR published_at IS NOT NULL",
            name="published_requires_timestamp",
        ),
        Index(
            "ix_case_studies_company_status_updated",
            "company_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_case_studies_company_industry_order",
            "company_id",
            "industry",
            "sort_order",
        ),
    )

    slug: Mapped[str] = mapped_column(String(96), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    background: Mapped[str] = mapped_column(Text, nullable=False)
    solution: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    client_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(2_048), nullable=True)
    visibility: Mapped[Visibility] = mapped_column(
        db_enum(Visibility, "case_study_visibility"),
        nullable=False,
        default=Visibility.PUBLIC,
        server_default=text("'public'"),
    )
    status: Mapped[ContentStatus] = mapped_column(
        db_enum(ContentStatus, "case_study_status"),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=text("'draft'"),
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class ContentPublicationRevision(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "content_publication_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "resource_type",
            "resource_id",
            "revision_number",
            name="uq_content_publication_revision_number",
        ),
        CheckConstraint(
            "resource_type IN ('product', 'case_study')",
            name="resource_type_supported",
        ),
        CheckConstraint("revision_number >= 1", name="revision_number_positive"),
        Index(
            "ix_content_publication_revisions_resource",
            "company_id",
            "resource_type",
            "resource_id",
            "revision_number",
        ),
    )

    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    published_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class EnterpriseContentDistribution(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    """Company default visibility for a published piece of shared content.

    The generic resource identifier deliberately has no polymorphic FK.  The
    service validates it against its typed source model, which keeps products,
    cases and knowledge documents independently evolvable.
    """

    __tablename__ = "enterprise_content_distributions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "resource_type",
            "resource_id",
            name="uq_enterprise_content_distributions_resource",
        ),
        Index(
            "ix_enterprise_content_distributions_company_resource",
            "company_id",
            "resource_type",
            "resource_id",
        ),
    )

    resource_type: Mapped[DistributedContentType] = mapped_column(
        db_enum(DistributedContentType, "distributed_content_type"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    is_default_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )


class CardContentOverride(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    """Per-card presentation override; source content itself is never copied."""

    __tablename__ = "card_content_overrides"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "card_id",
            "resource_type",
            "resource_id",
            name="uq_card_content_overrides_resource",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_card_content_overrides_scope_id"
        ),
        Index(
            "ix_card_content_overrides_card_resource",
            "card_id",
            "resource_type",
            "resource_id",
        ),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    resource_type: Mapped[DistributedContentType] = mapped_column(
        db_enum(DistributedContentType, "card_override_content_type"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    mode: Mapped[CardContentOverrideMode] = mapped_column(
        db_enum(CardContentOverrideMode, "card_content_override_mode"), nullable=False
    )
    # Whitelisted public presentation fields only.  Never a source body or visibility.
    custom_display: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)


class CardContentOverrideRevision(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    """Immutable snapshots make an override rollback auditable and deterministic."""

    __tablename__ = "card_content_override_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "override_id"],
            [
                "card_content_overrides.tenant_id",
                "card_content_overrides.company_id",
                "card_content_overrides.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint("override_id", "version", name="uq_card_content_override_revision"),
        Index("ix_card_content_override_revisions_override", "override_id", "version"),
    )

    override_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[CardContentOverrideMode] = mapped_column(
        db_enum(CardContentOverrideMode, "card_content_override_revision_mode"), nullable=False
    )
    custom_display: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)


class ForbiddenTopic(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "forbidden_topics"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_forbidden_topics_scope_id"),
        CheckConstraint(
            "action IN ('refuse', 'handoff', 'safe_template')",
            name="action_allowed",
        ),
        Index("ix_forbidden_topics_company_active", "company_id", "is_active", "updated_at"),
    )

    topic: Mapped[str] = mapped_column(String(240), nullable=False)
    match_terms: Mapped[list[str]] = mapped_column(
        ARRAY(String(160)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'refuse'"))
    safe_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )


class Visitor(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visitors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_visitors_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "anonymous_hash",
            name="uq_visitors_scope_anonymous_hash",
        ),
        CheckConstraint("char_length(anonymous_hash) = 64", name="anonymous_hash_sha256"),
        Index("ix_visitors_company_last_seen", "company_id", "last_seen_at"),
    )

    anonymous_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class VisitorProfile(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visitor_profiles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("visitor_id", name="uq_visitor_profiles_visitor_id"),
    )

    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mobile_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    mobile_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    email_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wechat_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    demand_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encryption_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class ConsentRecord(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_consent_records_scope_id"),
        Index("ix_consent_records_visitor_scope_recorded", "visitor_id", "scope", "recorded_at"),
    )

    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    scope: Mapped[ConsentScope] = mapped_column(
        db_enum(ConsentScope, "consent_scope"), nullable=False
    )
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class VisitorProfileSignal(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visitor_profile_signals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
            name="fk_visitor_profile_signals_visitor",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_visitor_profile_signals_scope_id"
        ),
        UniqueConstraint(
            "visitor_id", "kind", "label_hmac", name="uq_visitor_profile_signals_identity"
        ),
        CheckConstraint("strength >= 0 AND strength <= 1", name="strength_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("evidence_count >= 0", name="evidence_count_non_negative"),
        CheckConstraint("char_length(label_hmac) = 64", name="label_hmac_sha256"),
        Index("ix_visitor_profile_signals_visitor_last_seen", "visitor_id", "last_seen_at"),
        Index("ix_visitor_profile_signals_retention", "retention_expires_at"),
    )

    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    kind: Mapped[VisitorProfileSignalKind] = mapped_column(
        db_enum(VisitorProfileSignalKind, "visitor_profile_signal_kind"), nullable=False
    )
    label_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    label_hmac: Mapped[str] = mapped_column(String(64), nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    retention_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)


class VisitorProfileSignalSource(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "visitor_profile_signal_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "signal_id"],
            [
                "visitor_profile_signals.tenant_id",
                "visitor_profile_signals.company_id",
                "visitor_profile_signals.id",
            ],
            ondelete="CASCADE",
            name="fk_profile_signal_sources_signal",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "consent_id"],
            ["consent_records.tenant_id", "consent_records.company_id", "consent_records.id"],
            ondelete="RESTRICT",
            name="fk_profile_signal_sources_consent",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visit_id"],
            ["visits.tenant_id", "visits.company_id", "visits.id"],
            ondelete="RESTRICT",
            name="fk_profile_signal_sources_visit",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="RESTRICT",
            name="fk_profile_signal_sources_conversation",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "summary_id"],
            ["visit_summaries.tenant_id", "visit_summaries.company_id", "visit_summaries.id"],
            ondelete="RESTRICT",
            name="fk_profile_signal_sources_summary",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            ondelete="RESTRICT",
            name="fk_profile_signal_sources_message",
        ),
        UniqueConstraint(
            "signal_id", "summary_id", "message_id", name="uq_profile_signal_source_evidence"
        ),
        CheckConstraint("contribution >= 0 AND contribution <= 1", name="contribution_range"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="source_confidence_range"),
        Index("ix_profile_signal_sources_signal_observed", "signal_id", "observed_at"),
    )

    signal_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    consent_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    summary_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    contribution: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    retention_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Visit(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_visits_scope_id"),
        Index("ix_visits_card_started", "card_id", "started_at"),
        Index("ix_visits_company_started", "company_id", "started_at"),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class VisitEvent(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "visit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visit_id"],
            ["visits.tenant_id", "visits.company_id", "visits.id"],
            ondelete="CASCADE",
        ),
        Index("ix_visit_events_visit_occurred", "visit_id", "occurred_at"),
        Index("ix_visit_events_company_type_occurred", "company_id", "event_type", "occurred_at"),
    )

    visit_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visit_id"],
            ["visits.tenant_id", "visits.company_id", "visits.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_conversations_scope_id"),
        Index("ix_conversations_card_started", "card_id", "started_at"),
        Index("ix_conversations_company_status_updated", "company_id", "status", "updated_at"),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visit_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[ConversationStatus] = mapped_column(
        db_enum(ConversationStatus, "conversation_status"),
        nullable=False,
        default=ConversationStatus.ACTIVE,
        server_default=text("'active'"),
    )
    primary_intent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low", server_default=text("'low'")
    )


class Message(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_messages_scope_id"),
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        Index(
            "uq_messages_client_message",
            "conversation_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    role: Mapped[MessageRole] = mapped_column(db_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MessageStatus] = mapped_column(
        db_enum(MessageStatus, "message_status"),
        nullable=False,
        default=MessageStatus.COMPLETED,
        server_default=text("'completed'"),
    )
    content_redacted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    client_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PromptVersion(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["published_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_prompt_versions_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "name",
            "version_number",
            name="uq_prompt_versions_name_version",
        ),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_sha256"),
        Index("ix_prompt_versions_company_status_updated", "company_id", "status", "updated_at"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(120), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evaluation_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[PromptStatus] = mapped_column(
        db_enum(PromptStatus, "prompt_status"),
        nullable=False,
        default=PromptStatus.DRAFT,
        server_default=text("'draft'"),
    )
    published_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformLLMProfile(UUIDPrimaryKeyMixin, TimestampMixin, OptimisticVersionMixin, Base):
    """Platform-owned main Chat provider profile.

    Provider credentials are authenticated ciphertext.  This model deliberately
    has no plaintext key attribute and is not company-scoped: platform-only RLS
    controls writes while the API runtime receives read-only access so a public
    Chat request can resolve the selected profile without impersonation.
    """

    __tablename__ = "platform_llm_profiles"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("purpose = 'chat_main'", name="purpose_allowed"),
        CheckConstraint("btrim(provider) <> ''", name="provider_not_blank"),
        CheckConstraint("btrim(base_url) <> ''", name="base_url_not_blank"),
        CheckConstraint("btrim(model) <> ''", name="model_not_blank"),
        CheckConstraint(
            "thinking IN ('enabled', 'disabled')",
            name="thinking_allowed",
        ),
        CheckConstraint(
            "reasoning_effort IS NULL OR reasoning_effort IN ('high', 'max')",
            name="reasoning_effort_allowed",
        ),
        CheckConstraint(
            "timeout_seconds >= 2 AND timeout_seconds <= 120",
            name="timeout_seconds_range",
        ),
        CheckConstraint("max_retries >= 0 AND max_retries <= 5", name="max_retries_range"),
        CheckConstraint(
            "max_concurrency >= 1 AND max_concurrency <= 500",
            name="max_concurrency_range",
        ),
        CheckConstraint(
            "max_output_tokens >= 128 AND max_output_tokens <= 8192",
            name="max_output_tokens_range",
        ),
        CheckConstraint("temperature >= 0 AND temperature <= 2", name="temperature_range"),
        CheckConstraint(
            "thinking = 'disabled' OR temperature = 0.1",
            name="thinking_temperature_neutral",
        ),
        CheckConstraint("daily_budget_cny >= 0", name="daily_budget_non_negative"),
        CheckConstraint(
            "input_price_cny_per_million >= 0",
            name="input_price_non_negative",
        ),
        CheckConstraint(
            "output_price_cny_per_million >= 0",
            name="output_price_non_negative",
        ),
        CheckConstraint(
            "last_test_status IN ('untested', 'succeeded', 'failed')",
            name="last_test_status_allowed",
        ),
        CheckConstraint(
            "(last_test_status = 'untested' AND last_test_latency_ms IS NULL "
            "AND last_tested_at IS NULL) OR "
            "(last_test_status IN ('succeeded', 'failed') "
            "AND last_test_latency_ms >= 0 AND last_tested_at IS NOT NULL)",
            name="last_test_state_consistent",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "(api_key_ciphertext IS NULL AND api_key_key_ref IS NULL AND api_key_hint IS NULL) "
            "OR (api_key_ciphertext IS NOT NULL AND api_key_key_ref IS NOT NULL "
            "AND api_key_hint IS NOT NULL)",
            name="api_key_state",
        ),
        Index(
            "uq_platform_llm_profiles_name_normalized",
            func.lower(func.btrim(sql_text("name"))),
            unique=True,
        ),
        Index(
            "uq_platform_llm_profiles_one_active",
            "is_active",
            unique=True,
            postgresql_where=sql_text("is_active"),
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="chat_main",
        server_default=text("'chat_main'"),
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2_048), nullable=False)
    api_key_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_key_key_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    thinking: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="disabled",
        server_default=text("'disabled'"),
    )
    reasoning_effort: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
    )
    timeout_seconds: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        default=Decimal("30"),
        server_default=text("30"),
    )
    max_retries: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=2,
        server_default=text("2"),
    )
    max_concurrency: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
        server_default=text("20"),
    )
    max_output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1_000,
        server_default=text("1000"),
    )
    temperature: Mapped[Decimal] = mapped_column(
        Numeric(4, 3),
        nullable=False,
        default=Decimal("0.1"),
        server_default=text("0.1"),
    )
    daily_budget_cny: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("100"),
        server_default=text("100"),
    )
    input_price_cny_per_million: Mapped[Decimal] = mapped_column(
        Numeric(14, 6),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    output_price_cny_per_million: Mapped[Decimal] = mapped_column(
        Numeric(14, 6),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    allow_general_answers: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    faq_fast_path_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    last_test_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="untested",
        server_default=text("'untested'"),
    )
    last_test_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class PlatformOnboardingSession(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    Base,
):
    """Platform-owned handle for one isolated provisional enterprise scope."""

    __tablename__ = "platform_onboarding_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["admin_user_id"], ["users.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["admin_membership_id"], ["memberships.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(
            ["credential_id"], ["staff_credentials.id"], ondelete="RESTRICT"
        ),
        ForeignKeyConstraint(["initial_card_id"], ["cards.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", name="uq_platform_onboarding_tenant"),
        UniqueConstraint("company_id", name="uq_platform_onboarding_company"),
        UniqueConstraint("credential_id", name="uq_platform_onboarding_credential"),
        CheckConstraint(
            "status IN ('draft','processing','review','manual_required',"
            "'ready_to_confirm','confirmed','cancelled','expired','failed')",
            name="status_allowed",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL)",
            name="confirmed_state",
        ),
        CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name="cancelled_state",
        ),
        Index("ix_platform_onboarding_status_created", "status", "created_at"),
        Index(
            "ix_platform_onboarding_expiry",
            "expires_at",
            postgresql_where=sql_text(
                "status NOT IN ('confirmed','cancelled','expired','failed')"
            ),
        ),
    )

    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    admin_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    admin_membership_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    credential_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    initial_card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    tenant_slug: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    admin_account: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", server_default=text("'draft'")
    )
    import_batch_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)),
        nullable=False,
        default=list,
        server_default=text("'{}'::uuid[]"),
    )
    suggestions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    business_profile: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    confirmed_enterprise: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ModelConfig(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "model_configs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_model_configs_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "purpose",
            "provider",
            name="uq_model_configs_purpose_provider",
        ),
        CheckConstraint("timeout_ms > 0", name="timeout_positive"),
        CheckConstraint("max_concurrency > 0", name="concurrency_positive"),
        CheckConstraint("daily_budget_cny >= 0", name="budget_non_negative"),
    )

    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(160), nullable=False)
    endpoint_region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("30000"))
    max_retries: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("2"))
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    daily_budget_cny: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, server_default=text("0")
    )
    data_retention: Mapped[str] = mapped_column(
        String(40), nullable=False, server_default=text("'no_training'")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class AIRun(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "prompt_version_id"],
            ["prompt_versions.tenant_id", "prompt_versions.company_id", "prompt_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "model_config_id"],
            ["model_configs.tenant_id", "model_configs.company_id", "model_configs.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("message_id", name="uq_ai_runs_message_id"),
        CheckConstraint(
            "message_id IS NOT NULL OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)",
            name="source_reference_required",
        ),
        CheckConstraint("input_tokens >= 0 AND output_tokens >= 0", name="tokens_non_negative"),
        CheckConstraint("total_latency_ms >= 0", name="latency_non_negative"),
        Index("ix_ai_runs_company_created", "company_id", "created_at"),
        Index("ix_ai_runs_trace_id", "trace_id"),
        Index("ix_ai_runs_resource", "company_id", "resource_type", "resource_id"),
    )

    message_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    purpose: Mapped[str] = mapped_column(
        String(80), nullable=False, default="rag_answer", server_default=text("'rag_answer'")
    )
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    prompt_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    model_config_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    endpoint_region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    first_token_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estimated_cost_cny: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, server_default=text("0")
    )
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    status: Mapped[MessageStatus] = mapped_column(
        db_enum(MessageStatus, "ai_run_status"),
        nullable=False,
        default=MessageStatus.PENDING,
        server_default=text("'pending'"),
    )
    safety_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    retrieval_result: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeDocument(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "id", "current_version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.document_id",
                "knowledge_versions.id",
            ],
            name="fk_knowledge_documents_current_version",
            use_alter=True,
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_knowledge_documents_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "source_type",
            "source_id",
            name="uq_knowledge_documents_source",
        ),
        CheckConstraint(
            "status <> 'published' OR current_version_id IS NOT NULL",
            name="published_requires_current_version",
        ),
        Index(
            "ix_knowledge_documents_company_status_updated", "company_id", "status", "updated_at"
        ),
        Index(
            "ix_knowledge_documents_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )

    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ContentStatus] = mapped_column(
        db_enum(ContentStatus, "knowledge_document_status"),
        nullable=False,
        default=ContentStatus.DRAFT,
        server_default=text("'draft'"),
    )
    current_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class KnowledgeVersion(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.company_id",
                "knowledge_documents.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_knowledge_versions_scope_id"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "document_id",
            "id",
            name="uq_knowledge_versions_document_scope_id",
        ),
        UniqueConstraint(
            "document_id", "version_number", name="uq_knowledge_versions_document_version"
        ),
        CheckConstraint("version_number > 0", name="version_positive"),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_sha256"),
        CheckConstraint(
            "review_status <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="approval_state",
        ),
        Index(
            "ix_knowledge_versions_raw_text_fts",
            text("to_tsvector('simple', coalesce(raw_text, ''))"),
            postgresql_using="gin",
        ),
    )

    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    review_status: Mapped[ReviewStatus] = mapped_column(
        db_enum(ReviewStatus, "knowledge_review_status"),
        nullable=False,
        default=ReviewStatus.DRAFT,
        server_default=text("'draft'"),
    )
    reviewed_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeImportBatch(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "knowledge_import_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_knowledge_import_batches_scope_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "sequence_number",
            name="uq_knowledge_import_batches_company_sequence",
        ),
        CheckConstraint("sequence_number > 0", name="sequence_number_positive"),
        CheckConstraint("char_length(btrim(display_name)) > 0", name="display_name_non_empty"),
        CheckConstraint("total_items > 0", name="total_items_positive"),
        CheckConstraint(
            "pending_items >= 0 AND succeeded_items >= 0 AND failed_items >= 0",
            name="counts_non_negative",
        ),
        CheckConstraint(
            "pending_items + succeeded_items + failed_items = total_items",
            name="counts_match_total",
        ),
        Index("ix_knowledge_import_batches_company_created", "company_id", "created_at"),
    )

    requested_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    auto_publish: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    status: Mapped[KnowledgeImportBatchStatus] = mapped_column(
        db_enum(KnowledgeImportBatchStatus, "knowledge_import_batch_status"),
        nullable=False,
        default=KnowledgeImportBatchStatus.PENDING,
        server_default=text("'pending'"),
    )
    total_items: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_items: Mapped[int] = mapped_column(Integer, nullable=False)
    succeeded_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed_items: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeImportItem(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_import_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "batch_id"],
            [
                "knowledge_import_batches.tenant_id",
                "knowledge_import_batches.company_id",
                "knowledge_import_batches.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.company_id",
                "knowledge_documents.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "source_type IN ('pdf','docx','csv','pptx','xlsx','txt','md','html','htm',"
            "'png','jpg','jpeg','webp','tiff','bmp')",
            name="source_type_allowed",
        ),
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="attempts_valid"),
        CheckConstraint("char_length(payload_sha256) = 64", name="payload_sha256"),
        CheckConstraint(
            "status <> 'processing' OR (lock_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="processing_lease",
        ),
        Index("ix_knowledge_import_items_due", "status", "next_attempt_at", "created_at"),
        Index("ix_knowledge_import_items_batch", "batch_id", "created_at"),
    )

    batch_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auto_publish: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    parse_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending", server_default=text("'pending'")
    )
    publish_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[KnowledgeImportItemStatus] = mapped_column(
        db_enum(KnowledgeImportItemStatus, "knowledge_import_item_status"),
        nullable=False,
        default=KnowledgeImportItemStatus.PENDING,
        server_default=text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lock_token: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    document_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentImportRun(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "content_import_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "batch_id"],
            [
                "knowledge_import_batches.tenant_id",
                "knowledge_import_batches.company_id",
                "knowledge_import_batches.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint(
            "tenant_id", "company_id", "id", name="uq_content_import_runs_scope_id"
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "batch_id",
            name="uq_content_import_runs_scope_batch",
        ),
        CheckConstraint(
            "status IN ('processing','review','manual_required')",
            name="content_import_run_status_allowed",
        ),
        CheckConstraint("attempts >= 0 AND attempts <= 2", name="attempts_allowed"),
        Index("ix_content_import_runs_company_created", "company_id", "created_at"),
        Index("ix_content_import_runs_batch_created", "batch_id", "created_at"),
    )

    batch_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="processing", server_default=text("'processing'")
    )
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failure_code: Mapped[str | None] = mapped_column(String(500), nullable=True)
    counts: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ContentImportCandidate(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "content_import_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "run_id"],
            [
                "content_import_runs.tenant_id",
                "content_import_runs.company_id",
                "content_import_runs.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "id",
            name="uq_content_import_candidates_scope_id",
        ),
        UniqueConstraint("run_id", "fingerprint", name="uq_content_import_candidates_run_hash"),
        CheckConstraint(
            "category IN ('enterprise_profile','products','case_studies','faqs','unclassified')",
            name="content_import_candidate_category_allowed",
        ),
        CheckConstraint(
            "status IN ('pending_review','accepted','ignored','conflict')",
            name="content_import_candidate_status_allowed",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        CheckConstraint("char_length(fingerprint) = 64", name="fingerprint_sha256"),
        Index("ix_content_import_candidates_run_status", "run_id", "status", "created_at"),
        Index(
            "ix_content_import_candidates_company_category",
            "company_id",
            "category",
            "status",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="pending_review",
        server_default=text("'pending_review'"),
    )
    target_resource_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id"],
            [
                "knowledge_documents.tenant_id",
                "knowledge_documents.company_id",
                "knowledge_documents.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "document_id", "version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.document_id",
                "knowledge_versions.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_knowledge_chunks_scope_id"),
        UniqueConstraint("version_id", "ordinal", name="uq_knowledge_chunks_version_ordinal"),
        CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
        CheckConstraint("token_count > 0", name="token_count_positive"),
        CheckConstraint("char_length(content_hash) = 64", name="content_hash_sha256"),
        CheckConstraint(
            "(embedding IS NULL) = (embedding_model IS NULL)",
            name="embedding_metadata",
        ),
        Index(
            "ix_knowledge_chunks_scope_filter",
            "company_id",
            "visibility",
            "is_active",
            "version_id",
        ),
        Index(
            "ix_knowledge_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_where=text("embedding IS NOT NULL"),
        ),
        Index(
            "ix_knowledge_chunks_text_fts",
            "search_tsv",
            postgresql_using="gin",
        ),
        Index(
            "ix_knowledge_chunks_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "gin_trgm_ops"},
        ),
    )

    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    search_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(text, ''))", persisted=True),
    )
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(160), nullable=True)
    visibility: Mapped[Visibility] = mapped_column(
        db_enum(Visibility, "knowledge_visibility"),
        nullable=False,
        default=Visibility.PUBLIC,
        server_default=sql_text("'public'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(String(160), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )


class MessageCitation(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "message_citations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "chunk_id"],
            ["knowledge_chunks.tenant_id", "knowledge_chunks.company_id", "knowledge_chunks.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("message_id", "chunk_id", name="uq_message_citations_message_chunk"),
        CheckConstraint("rank > 0", name="rank_positive"),
        CheckConstraint("score >= -1 AND score <= 1", name="score_cosine_range"),
        CheckConstraint("char_length(snapshot_hash) = 64", name="snapshot_hash_sha256"),
        Index("ix_message_citations_message_rank", "message_id", "rank"),
    )

    message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    chunk_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    snapshot_text: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeIndexJob(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_index_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "version_id", "embedding_model", name="uq_knowledge_index_jobs_version_model"
        ),
        CheckConstraint("attempt >= 0", name="attempt_non_negative"),
        Index(
            "ix_knowledge_index_jobs_company_status_created", "company_id", "status", "created_at"
        ),
    )

    version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[IndexJobStatus] = mapped_column(
        db_enum(IndexJobStatus, "knowledge_index_job_status"),
        nullable=False,
        default=IndexJobStatus.PENDING,
        server_default=text("'pending'"),
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeGap(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "knowledge_gaps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "approved_version_id"],
            [
                "knowledge_versions.tenant_id",
                "knowledge_versions.company_id",
                "knowledge_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        CheckConstraint("char_length(normalized_question_hash) = 64", name="question_hash_sha256"),
        CheckConstraint("occurrence_count > 0", name="occurrence_count_positive"),
        Index("ix_knowledge_gaps_company_status_updated", "company_id", "status", "updated_at"),
        Index("ix_knowledge_gaps_company_question_hash", "company_id", "normalized_question_hash"),
        Index(
            "ix_knowledge_gaps_question_trgm",
            "question",
            postgresql_using="gin",
            postgresql_ops={"question": "gin_trgm_ops"},
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    normalized_question_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[KnowledgeGapStatus] = mapped_column(
        db_enum(KnowledgeGapStatus, "knowledge_gap_status"),
        nullable=False,
        default=KnowledgeGapStatus.PENDING,
        server_default=text("'pending'"),
    )
    suggested_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class VisitSummary(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "visit_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "last_message_id"],
            ["messages.tenant_id", "messages.company_id", "messages.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "prompt_version_id"],
            ["prompt_versions.tenant_id", "prompt_versions.company_id", "prompt_versions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_visit_summaries_scope_id"),
        UniqueConstraint(
            "conversation_id",
            "last_message_id",
            "prompt_version_id",
            name="uq_visit_summaries_idempotency",
        ),
        Index(
            "uq_visit_summaries_current_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    last_message_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    prompt_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    interests: Mapped[list[str]] = mapped_column(
        ARRAY(String(160)), nullable=False, default=list, server_default=text("'{}'::varchar[]")
    )
    strength: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)), nullable=False
    )
    is_current: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    stale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class Lead(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "leads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "card_id"],
            ["cards.tenant_id", "cards.company_id", "cards.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.company_id", "conversations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        UniqueConstraint("tenant_id", "company_id", "id", name="uq_leads_scope_id"),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high')",
            name="priority_allowed",
        ),
        Index("ix_leads_company_status_created", "company_id", "status", "created_at"),
        Index("ix_leads_owner_status_created", "owner_user_id", "status", "created_at"),
    )

    card_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    owner_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[LeadStatus] = mapped_column(
        db_enum(LeadStatus, "lead_status"),
        nullable=False,
        default=LeadStatus.NEW,
        server_default=text("'new'"),
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="medium",
        server_default=text("'medium'"),
    )
    requirement_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    interest_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(160)),
        nullable=False,
        default=list,
        server_default=text("'{}'::varchar[]"),
    )
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeadFollowup(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "lead_followups"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "lead_id"],
            ["leads.tenant_id", "leads.company_id", "leads.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
        CheckConstraint(
            "followup_type IN ('note', 'call', 'message', 'meeting', 'status_change')",
            name="type_allowed",
        ),
        Index("ix_lead_followups_lead_created", "lead_id", "created_at"),
    )

    lead_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    followup_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PrivacyRequest(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "privacy_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "visitor_id"],
            ["visitors.tenant_id", "visitors.company_id", "visitors.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["handled_by"], ["users.id"], ondelete="SET NULL"),
        Index("ix_privacy_requests_company_status_created", "company_id", "status", "created_at"),
        Index("ix_privacy_requests_visitor_created", "visitor_id", "created_at"),
    )

    visitor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    request_type: Mapped[PrivacyRequestType] = mapped_column(
        db_enum(PrivacyRequestType, "privacy_request_type"),
        nullable=False,
    )
    status: Mapped[PrivacyRequestStatus] = mapped_column(
        db_enum(PrivacyRequestStatus, "privacy_request_status"),
        nullable=False,
        default=PrivacyRequestStatus.PENDING,
        server_default=text("'pending'"),
    )
    note_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    encryption_key_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    verification_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    handled_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )


class Notification(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        Index(
            "ix_notifications_recipient_read_created",
            "recipient_user_id",
            "read_at",
            "created_at",
        ),
    )

    recipient_user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class IdempotencyKey(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id", "company_id", "scope", "key", name="uq_idempotency_keys_scope_key"
        ),
        CheckConstraint("char_length(request_hash) = 64", name="request_hash_sha256"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )

    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        db_enum(IdempotencyStatus, "idempotency_status"),
        nullable=False,
        default=IdempotencyStatus.PROCESSING,
        server_default=text("'processing'"),
    )
    response_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        CheckConstraint("char_length(entry_hash) = 64", name="entry_hash_sha256"),
        CheckConstraint(
            "previous_hash IS NULL OR char_length(previous_hash) = 64",
            name="previous_hash_sha256",
        ),
        Index("ix_audit_logs_company_created", "company_id", "created_at"),
        Index("ix_audit_logs_resource", "company_id", "resource_type", "resource_id"),
        Index("ix_audit_logs_trace_id", "trace_id"),
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SecurityEvent(UUIDPrimaryKeyMixin, Base):
    """Unscoped authentication audit boundary.

    Failed logins do not yet have a trusted tenant scope, so they cannot be
    represented safely in a company-scoped audit row. Only keyed hashes and
    identifiers are stored here, never credentials, tokens, or raw IP values.
    """

    __tablename__ = "security_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('succeeded', 'failed', 'blocked')",
            name="outcome_allowed",
        ),
        Index("ix_security_events_type_occurred", "event_type", "occurred_at"),
        Index("ix_security_events_account_occurred", "account_hash", "occurred_at"),
        Index("ix_security_events_ip_occurred", "request_ip_hash", "occurred_at"),
    )

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    account_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    membership_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    tenant_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    company_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    event_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class OutboxEvent(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "deduplication_key",
            name="uq_outbox_events_deduplication_key",
        ),
        UniqueConstraint(
            "tenant_id",
            "company_id",
            "id",
            name="uq_outbox_events_scope_id",
        ),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint(
            """
            status <> 'processing' OR (
              locked_at IS NOT NULL
              AND locked_by IS NOT NULL
              AND lock_token IS NOT NULL
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at > locked_at
            )
            """,
            name="processing_lease",
        ),
        Index("ix_outbox_events_dispatch", "status", "available_at", "created_at"),
        Index(
            "ix_outbox_events_lease_recovery",
            "status",
            "lease_expires_at",
            "available_at",
            "created_at",
        ),
        Index("ix_outbox_events_aggregate", "company_id", "aggregate_type", "aggregate_id"),
    )

    aggregate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    aggregate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    headers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    deduplication_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        db_enum(OutboxStatus, "outbox_status"),
        nullable=False,
        default=OutboxStatus.PENDING,
        server_default=text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lock_token: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class OutboxDelivery(UUIDPrimaryKeyMixin, CompanyScopeMixin, Base):
    __tablename__ = "outbox_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "event_id"],
            ["outbox_events.tenant_id", "outbox_events.company_id", "outbox_events.id"],
            ondelete="CASCADE",
            name="fk_outbox_deliveries_event_scope",
        ),
        UniqueConstraint(
            "event_id",
            "handler_name",
            name="uq_outbox_deliveries_event_handler",
        ),
        CheckConstraint("char_length(result_hash) = 64", name="result_hash_sha256"),
        Index("ix_outbox_deliveries_company_completed", "company_id", "completed_at"),
    )

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    handler_name: Mapped[str] = mapped_column(String(160), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkerJobResult(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "worker_job_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "event_id"],
            ["outbox_events.tenant_id", "outbox_events.company_id", "outbox_events.id"],
            ondelete="CASCADE",
            name="fk_worker_job_results_event_scope",
        ),
        UniqueConstraint("event_id", name="uq_worker_job_results_event"),
        CheckConstraint("schema_version > 0", name="schema_version_positive"),
        CheckConstraint(
            "status IN ('completed', 'passed', 'failed_gate')",
            name="status_allowed",
        ),
        CheckConstraint("char_length(report_hash) = 64", name="report_hash_sha256"),
        Index("ix_worker_job_results_company_created", "company_id", "created_at"),
    )

    event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    result_type: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    report_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DataExportRequest(UUIDPrimaryKeyMixin, TimestampMixin, CompanyScopeMixin, Base):
    __tablename__ = "data_export_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        ForeignKeyConstraint(
            ["tenant_id", "company_id", "outbox_event_id"],
            ["outbox_events.tenant_id", "outbox_events.company_id", "outbox_events.id"],
            ondelete="RESTRICT",
            name="fk_data_export_requests_outbox_scope",
        ),
        UniqueConstraint("outbox_event_id", name="uq_data_export_requests_outbox_event"),
        CheckConstraint("scope_kind IN ('company', 'card_owner')", name="scope_kind_allowed"),
        CheckConstraint(
            "scope_kind = 'company' OR owner_user_id IS NOT NULL",
            name="owner_scope_requires_user",
        ),
        CheckConstraint(
            "NOT include_sensitive OR scope_kind = 'company'",
            name="sensitive_requires_company_scope",
        ),
        CheckConstraint("row_count IS NULL OR row_count >= 0", name="row_count_non_negative"),
        CheckConstraint(
            "file_sha256 IS NULL OR char_length(file_sha256) = 64",
            name="file_sha256",
        ),
        CheckConstraint(
            "status <> 'completed' OR (completed_at IS NOT NULL AND expires_at IS NOT NULL "
            "AND file_ciphertext IS NOT NULL AND file_sha256 IS NOT NULL "
            "AND file_name IS NOT NULL AND row_count IS NOT NULL)",
            name="completed_artifact_required",
        ),
        Index(
            "ix_data_export_requests_requester_created",
            "company_id",
            "requested_by",
            "created_at",
        ),
        Index("ix_data_export_requests_expiry", "status", "expires_at"),
    )

    requested_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    requested_role: Mapped[str] = mapped_column(String(40), nullable=False)
    export_type: Mapped[DataExportType] = mapped_column(
        db_enum(DataExportType, "data_export_type"), nullable=False
    )
    status: Mapped[DataExportStatus] = mapped_column(
        db_enum(DataExportStatus, "data_export_status"),
        nullable=False,
        default=DataExportStatus.PENDING,
        server_default=text("'pending'"),
    )
    scope_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    owner_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    include_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    outbox_event_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    encryption_key_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ScheduledPublishJob(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OptimisticVersionMixin,
    CompanyScopeMixin,
    Base,
):
    __tablename__ = "scheduled_publish_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            ["companies.tenant_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(["scheduled_by"], ["users.id"], ondelete="RESTRICT"),
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="attempts_valid"),
        CheckConstraint(
            "status <> 'processing' OR (lock_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="processing_lease",
        ),
        CheckConstraint(
            "status <> 'completed' OR completed_at IS NOT NULL", name="completed_timestamp"
        ),
        Index("ix_scheduled_publish_jobs_due", "status", "next_attempt_at", "scheduled_at"),
        Index("ix_scheduled_publish_jobs_company_created", "company_id", "created_at"),
        Index(
            "uq_scheduled_publish_jobs_active_resource",
            "tenant_id",
            "company_id",
            "resource_type",
            "resource_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'processing', 'failed')"),
        ),
    )

    resource_type: Mapped[ScheduledPublishResourceType] = mapped_column(
        db_enum(ScheduledPublishResourceType, "scheduled_publish_resource_type"), nullable=False
    )
    resource_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    target_version: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    scheduled_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[ScheduledPublishStatus] = mapped_column(
        db_enum(ScheduledPublishStatus, "scheduled_publish_status"),
        nullable=False,
        default=ScheduledPublishStatus.PENDING,
        server_default=text("'pending'"),
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("6"))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lock_token: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = [
    "AIRun",
    "AuditLog",
    "AuthSession",
    "Card",
    "CardContactField",
    "CaseStudy",
    "Company",
    "ConsentRecord",
    "Conversation",
    "DataExportRequest",
    "DataExportStatus",
    "DataExportType",
    "ForbiddenTopic",
    "IdempotencyKey",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeGap",
    "KnowledgeImportBatch",
    "KnowledgeImportBatchStatus",
    "KnowledgeImportItem",
    "KnowledgeImportItemStatus",
    "KnowledgeIndexJob",
    "KnowledgeVersion",
    "Lead",
    "LeadFollowup",
    "LeadStatus",
    "Membership",
    "Message",
    "MessageCitation",
    "ModelConfig",
    "Notification",
    "OutboxDelivery",
    "OutboxEvent",
    "PrivacyRequest",
    "PrivacyRequestStatus",
    "PrivacyRequestType",
    "Product",
    "PromptVersion",
    "SecurityEvent",
    "ScheduledPublishJob",
    "ScheduledPublishResourceType",
    "ScheduledPublishStatus",
    "StaffCredential",
    "Tenant",
    "User",
    "Visit",
    "VisitEvent",
    "Visitor",
    "VisitorProfile",
    "VisitSummary",
    "WeComCallbackEvent",
    "WeComCardContactWay",
    "WeComCustomerLink",
    "WeComEnterpriseAuthorization",
    "WeComEnterpriseScope",
    "WeComUserBinding",
    "WorkerJobResult",
]
