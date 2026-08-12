from __future__ import annotations

import ipaddress
import json
import re
import uuid
from datetime import datetime
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ContentStatusValue = Literal["draft", "review_pending", "published", "archived"]
CardKindValue = Literal["enterprise", "employee"]
VisibilityValue = Literal["public", "authenticated", "internal"]
ForbiddenAction = Literal["refuse", "handoff", "safe_template"]


class CatalogStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def validate_safe_asset_url(value: str | None) -> str | None:
    """Allow first-party paths or public HTTPS assets, never local/private destinations."""

    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if any(ord(character) < 32 for character in candidate) or "\\" in candidate:
        raise ValueError("asset URL contains unsafe characters")
    if candidate.startswith("/"):
        if candidate.startswith("//"):
            raise ValueError("protocol-relative asset URLs are not allowed")
        return candidate

    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("remote asset URLs must use HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("asset URLs must not contain credentials")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("local asset hosts are not allowed")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise ValueError("private or reserved asset addresses are not allowed")
    return candidate


def validate_json_settings(value: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("settings must contain JSON-compatible values") from exc
    if len(encoded.encode("utf-8")) > 32_768:
        raise ValueError("settings must not exceed 32 KiB")
    return value


class ProductWriteFields(CatalogStrictModel):
    slug: str = Field(
        min_length=3,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$",
    )
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    summary: str = Field(min_length=1, max_length=5_000)
    detail: str = Field(min_length=1, max_length=100_000)
    audience: str | None = Field(default=None, max_length=5_000)
    price_boundary: str | None = Field(default=None, max_length=2_000)
    image_url: str | None = Field(default=None, max_length=2_048)
    visibility: VisibilityValue = "public"
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    settings: dict[str, Any] = Field(default_factory=dict)

    _validate_image_url = field_validator("image_url")(validate_safe_asset_url)
    _validate_settings = field_validator("settings")(validate_json_settings)


class CreateProductRequest(ProductWriteFields):
    pass


class UpdateProductRequest(ProductWriteFields):
    pass


class ProductRecord(ProductWriteFields):
    id: uuid.UUID
    status: ContentStatusValue
    published_at: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ProductEnvelope(CatalogStrictModel):
    data: ProductRecord


class ProductListEnvelope(CatalogStrictModel):
    data: list[ProductRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class PublicProductRecord(CatalogStrictModel):
    slug: str
    name: str
    category: str | None = None
    summary: str
    detail: str
    audience: str | None = None
    price_boundary: str | None = None
    image_url: str | None = None
    sort_order: int = Field(ge=0)
    published_at: datetime


class PublicProductEnvelope(CatalogStrictModel):
    data: PublicProductRecord


class PublicProductListEnvelope(CatalogStrictModel):
    data: list[PublicProductRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class CaseStudyWriteFields(CatalogStrictModel):
    slug: str = Field(
        min_length=3,
        max_length=96,
        pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$",
    )
    title: str = Field(min_length=1, max_length=240)
    industry: str | None = Field(default=None, max_length=120)
    background: str = Field(min_length=1, max_length=50_000)
    solution: str = Field(min_length=1, max_length=50_000)
    result: str = Field(min_length=1, max_length=50_000)
    client_display_name: str | None = Field(default=None, max_length=200)
    image_url: str | None = Field(default=None, max_length=2_048)
    visibility: VisibilityValue = "public"
    sort_order: int = Field(default=0, ge=0, le=1_000_000)
    settings: dict[str, Any] = Field(default_factory=dict)

    _validate_image_url = field_validator("image_url")(validate_safe_asset_url)
    _validate_settings = field_validator("settings")(validate_json_settings)


class CreateCaseStudyRequest(CaseStudyWriteFields):
    pass


class UpdateCaseStudyRequest(CaseStudyWriteFields):
    pass


class CaseStudyRecord(CaseStudyWriteFields):
    id: uuid.UUID
    status: ContentStatusValue
    published_at: datetime | None = None
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class CaseStudyEnvelope(CatalogStrictModel):
    data: CaseStudyRecord


class CaseStudyListEnvelope(CatalogStrictModel):
    data: list[CaseStudyRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class PublicCaseStudyRecord(CatalogStrictModel):
    slug: str
    title: str
    industry: str | None = None
    background: str
    solution: str
    result: str
    client_display_name: str | None = None
    image_url: str | None = None
    sort_order: int = Field(ge=0)
    published_at: datetime


class PublicCaseStudyEnvelope(CatalogStrictModel):
    data: PublicCaseStudyRecord


class PublicCaseStudyListEnvelope(CatalogStrictModel):
    data: list[PublicCaseStudyRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class ForbiddenTopicWriteFields(CatalogStrictModel):
    topic: str = Field(min_length=1, max_length=240)
    match_terms: list[str] = Field(default_factory=list, max_length=64)
    action: ForbiddenAction = "refuse"
    safe_response: str | None = Field(default=None, max_length=5_000)

    @field_validator("match_terms")
    @classmethod
    def normalize_match_terms(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            term = value.strip()
            if not term or len(term) > 160:
                raise ValueError("match terms must contain 1-160 characters")
            key = term.casefold()
            if key not in seen:
                normalized.append(term)
                seen.add(key)
        return normalized

    @model_validator(mode="after")
    def require_safe_template(self) -> Self:
        if self.action == "safe_template" and not self.safe_response:
            raise ValueError("safe_response is required for safe_template")
        return self


class CreateForbiddenTopicRequest(ForbiddenTopicWriteFields):
    is_active: bool = True


class UpdateForbiddenTopicRequest(ForbiddenTopicWriteFields):
    pass


class ForbiddenTopicRecord(ForbiddenTopicWriteFields):
    id: uuid.UUID
    is_active: bool
    version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class ForbiddenTopicEnvelope(CatalogStrictModel):
    data: ForbiddenTopicRecord


class ForbiddenTopicListEnvelope(CatalogStrictModel):
    data: list[ForbiddenTopicRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


CardContactKindValue = Literal[
    "phone",
    "wechat",
    "email",
    "location",
    "website",
    "other",
]


class CardContactItem(CatalogStrictModel):
    id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",
    )
    kind: CardContactKindValue = "other"
    label: str = Field(min_length=1, max_length=40)
    value: str = Field(min_length=1, max_length=240)
    href: str | None = Field(default=None, max_length=2_048)

    @field_validator("href")
    @classmethod
    def validate_contact_href(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        if not candidate:
            return None
        if any(ord(character) < 32 for character in candidate) or "\\" in candidate:
            raise ValueError("contact href contains unsafe characters")
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() not in {"https", "tel", "mailto"}:
            raise ValueError("contact href must use https, tel or mailto")
        return candidate


class CardWriteFields(CatalogStrictModel):
    display_name: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=200)
    avatar_url: str | None = Field(default=None, max_length=2_048)
    assistant_name: str | None = Field(default=None, max_length=120)
    welcome_message: str | None = Field(default=None, max_length=2_000)
    suggested_questions: list[str] = Field(default_factory=list, max_length=6)
    policy_versions: dict[str, str] = Field(default_factory=dict)
    identity_titles: list[str] = Field(default_factory=list, max_length=8)
    contact_fields: list[CardContactItem] = Field(default_factory=list, max_length=8)
    employee_contact_visibility: list[Literal["mobile", "email"]] = Field(
        default_factory=list,
        max_length=2,
    )

    _validate_avatar_url = field_validator("avatar_url")(validate_safe_asset_url)

    @field_validator("suggested_questions")
    @classmethod
    def validate_suggested_questions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 200 for value in values):
            raise ValueError("suggested questions must contain 1-200 characters")
        return [value.strip() for value in values]

    @field_validator("policy_versions")
    @classmethod
    def validate_policy_versions(cls, values: dict[str, str]) -> dict[str, str]:
        allowed = {
            "privacy",
            "chat_notice",
            "lead_consent",
            "profile_personalization",
        }
        if set(values) - allowed:
            raise ValueError("unsupported policy version key")
        if any(not value.strip() or len(value) > 64 for value in values.values()):
            raise ValueError("policy versions must contain 1-64 characters")
        return {key: value.strip() for key, value in values.items()}

    @field_validator("employee_contact_visibility")
    @classmethod
    def validate_employee_contact_visibility(
        cls,
        values: list[Literal["mobile", "email"]],
    ) -> list[Literal["mobile", "email"]]:
        return list(dict.fromkeys(values))

    @field_validator("identity_titles")
    @classmethod
    def validate_identity_titles(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            title = value.strip()
            key = title.casefold()
            if not title or len(title) > 80:
                raise ValueError("identity titles must contain 1-80 characters")
            if key not in seen:
                normalized.append(title)
                seen.add(key)
        return normalized

    @field_validator("contact_fields")
    @classmethod
    def validate_contact_fields(cls, values: list[CardContactItem]) -> list[CardContactItem]:
        ids = [item.id for item in values if item.id is not None]
        if len(set(ids)) != len(ids):
            raise ValueError("contact field ids must be unique")
        return values


class UpdateManagedCardRequest(CardWriteFields):
    card_kind: CardKindValue
    owner_user_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_card_identity(self) -> Self:
        if self.card_kind == "enterprise" and self.owner_user_id is not None:
            raise ValueError("enterprise cards must not have an employee owner")
        if self.card_kind == "employee" and self.owner_user_id is None:
            raise ValueError("employee cards require an owner")
        return self


EnterpriseTemplateBlockType = Literal[
    "identity",
    "rich_text",
    "business_collection",
    "image_gallery",
    "video_link",
    "case_collection",
    "trust_panel",
    "faq",
    "cta",
    "ai_assistant",
    "action_collection",
]

EnterpriseTemplateLayoutVariant = Literal[
    "auto",
    "list",
    "grid",
    "carousel",
    "featured",
    "mosaic",
    "horizontal",
    "vertical",
]
EnterpriseTemplateActionTargetType = Literal[
    "external_url",
    "internal_path",
    "phone",
    "map",
]

EnterpriseTemplateActionTemplate = Literal[
    "shortcuts",
    "media",
    "event",
    "banner",
    "articles",
    "video",
    "buttons",
]


class EnterpriseTemplateBackground(CatalogStrictModel):
    asset_url: str | None = Field(default=None, max_length=2_048)
    fit: Literal["cover", "contain", "custom"] = "cover"
    position: Literal[
        "center",
        "top",
        "bottom",
        "left",
        "right",
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
    ] = "center"
    aspect_ratio: Literal["auto", "16:9", "4:3", "3:2", "1:1"] = "auto"
    focal_x: float = Field(default=50, ge=0, le=100)
    focal_y: float = Field(default=50, ge=0, le=100)
    scale: float = Field(default=1, ge=0.5, le=2)
    opacity: float = Field(default=1, ge=0, le=1)
    overlay: Literal["none", "light", "dark", "brand"] = "none"

    _validate_asset = field_validator("asset_url")(validate_safe_asset_url)


class EnterpriseTemplatePresentation(CatalogStrictModel):
    identity_layout: Literal["horizontal", "vertical"] = "horizontal"
    background: EnterpriseTemplateBackground | None = None


class EnterpriseTemplateActionItem(CatalogStrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    summary: str | None = Field(default=None, max_length=500)
    label: str | None = Field(default=None, max_length=80)
    tag: str | None = Field(default=None, max_length=80)
    icon: Literal["external", "building", "calendar", "file", "play"] | None = None
    date: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=80)
    duration: str | None = Field(default=None, max_length=24)
    image_url: str | None = Field(default=None, max_length=2_048)
    target_type: EnterpriseTemplateActionTargetType
    target_value: str = Field(min_length=1, max_length=2_048)
    open_mode: Literal["self", "new_tab"] = "self"

    _validate_image = field_validator("image_url")(validate_safe_asset_url)

    @model_validator(mode="after")
    def validate_action_target(self) -> Self:
        value = self.target_value.strip()
        if any(ord(character) < 32 for character in value) or "\\" in value:
            raise ValueError("action target contains unsafe characters")
        if self.target_type in {"external_url", "map"}:
            self.target_value = validate_safe_asset_url(value) or ""
        elif self.target_type == "internal_path":
            parsed = urlsplit(value)
            if (
                not value.startswith("/")
                or value.startswith("//")
                or parsed.scheme
                or parsed.netloc
                or any(part == ".." for part in parsed.path.split("/"))
            ):
                raise ValueError("internal action targets must be safe absolute paths")
            self.target_value = value
        else:
            if not re.fullmatch(r"\+?[0-9][0-9() -]{4,24}", value):
                raise ValueError("phone action targets must contain a valid phone number")
            self.target_value = value
        if self.open_mode == "new_tab" and self.target_type in {"phone", "internal_path"}:
            raise ValueError("phone and internal actions must open in the current context")
        return self


class EnterpriseTemplateMetric(CatalogStrictModel):
    value: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)


class EnterpriseTemplateCaseItem(CatalogStrictModel):
    id: uuid.UUID
    slug: str = Field(min_length=3, max_length=96)
    title: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=5_000)
    background: str | None = Field(default=None, max_length=5_000)
    solution: str | None = Field(default=None, max_length=5_000)
    result: str | None = Field(default=None, max_length=5_000)
    client_name: str | None = Field(default=None, max_length=200)
    metrics: list[EnterpriseTemplateMetric] = Field(default_factory=list, max_length=3)
    image_url: str | None = Field(default=None, max_length=2_048)
    cta_label: str | None = Field(default=None, max_length=80)

    _validate_image = field_validator("image_url")(validate_safe_asset_url)


class EnterpriseTemplateProductItem(CatalogStrictModel):
    id: uuid.UUID
    slug: str = Field(min_length=3, max_length=96)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=5_000)
    image_url: str | None = Field(default=None, max_length=2_048)
    cta_label: str | None = Field(default=None, max_length=80)

    _validate_image = field_validator("image_url")(validate_safe_asset_url)


class EnterpriseTemplateGalleryItem(CatalogStrictModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    image_url: str = Field(min_length=1, max_length=2_048)
    title: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    time_label: str | None = Field(default=None, max_length=80)
    period_label: str | None = Field(default=None, max_length=80)
    badge_mode: Literal["title", "time", "period", "custom", "none"] = "title"
    badge_text: str | None = Field(default=None, max_length=80)
    alt_text: str | None = Field(default=None, max_length=160)
    link_url: str | None = Field(default=None, max_length=2_048)

    _validate_image = field_validator("image_url")(validate_safe_asset_url)

    @field_validator("link_url")
    @classmethod
    def validate_link_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return validate_safe_asset_url(value.strip())


class EnterpriseTemplateProductOverride(CatalogStrictModel):
    id: uuid.UUID
    title: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=5_000)
    image_url: str | None = Field(default=None, max_length=2_048)
    cta_label: str | None = Field(default=None, max_length=80)

    _validate_image = field_validator("image_url")(validate_safe_asset_url)


class EnterpriseTemplateCaseOverride(CatalogStrictModel):
    id: uuid.UUID
    title: str | None = Field(default=None, max_length=240)
    industry: str | None = Field(default=None, max_length=120)
    client_name: str | None = Field(default=None, max_length=200)
    background: str | None = Field(default=None, max_length=5_000)
    solution: str | None = Field(default=None, max_length=5_000)
    summary: str | None = Field(default=None, max_length=5_000)
    result: str | None = Field(default=None, max_length=5_000)
    metrics: list[EnterpriseTemplateMetric] = Field(default_factory=list, max_length=3)
    image_url: str | None = Field(default=None, max_length=2_048)
    cta_label: str | None = Field(default=None, max_length=80)

    _validate_image = field_validator("image_url")(validate_safe_asset_url)


class EnterpriseTemplateBlock(CatalogStrictModel):
    """A deliberately small, safe block contract for public enterprise cards."""

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    type: EnterpriseTemplateBlockType
    visible: bool = True
    show_title: bool = True
    directory_enabled: bool = True
    sort_order: int = Field(default=0, ge=0, le=10_000)
    layout_variant: EnterpriseTemplateLayoutVariant = "auto"
    item_limit: int | None = Field(default=None, ge=1, le=12)
    action_template: EnterpriseTemplateActionTemplate | None = None
    presentation: EnterpriseTemplatePresentation | None = None
    title: str | None = Field(default=None, max_length=160)
    body: str | None = Field(default=None, max_length=8_000)
    image_urls: list[str] = Field(default_factory=list, max_length=12)
    gallery_items: list[EnterpriseTemplateGalleryItem] = Field(default_factory=list, max_length=12)
    video_url: str | None = Field(default=None, max_length=2_048)
    video_cover_url: str | None = Field(default=None, max_length=2_048)
    product_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)
    product_items: list[EnterpriseTemplateProductItem] = Field(default_factory=list, max_length=12)
    product_overrides: list[EnterpriseTemplateProductOverride] = Field(
        default_factory=list, max_length=12
    )
    case_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)
    case_items: list[EnterpriseTemplateCaseItem] = Field(default_factory=list, max_length=12)
    case_overrides: list[EnterpriseTemplateCaseOverride] = Field(
        default_factory=list, max_length=12
    )
    faq_mode: Literal["all_published", "selected"] | None = None
    faq_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=30)
    cta_label: str | None = Field(default=None, max_length=80)
    cta_url: str | None = Field(default=None, max_length=2_048)
    action_items: list[EnterpriseTemplateActionItem] = Field(default_factory=list, max_length=12)

    _validate_images = field_validator("image_urls")(
        lambda values: [validate_safe_asset_url(value) for value in values]
    )
    _validate_cover = field_validator("video_cover_url")(validate_safe_asset_url)

    @field_validator("cta_url")
    @classmethod
    def validate_https_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        parsed = urlsplit(value.strip())
        if parsed.scheme.casefold() != "https" or not parsed.hostname:
            raise ValueError("external links must use HTTPS")
        return validate_safe_asset_url(value.strip())

    @field_validator("video_url")
    @classmethod
    def validate_video_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        candidate = value.strip()
        parsed = urlsplit(candidate)
        if not parsed.scheme and not parsed.netloc:
            return validate_safe_asset_url(candidate)
        if parsed.scheme.casefold() != "https" or not parsed.hostname:
            raise ValueError("external video links must use HTTPS")
        return validate_safe_asset_url(candidate)

    @model_validator(mode="after")
    def validate_block_shape(self) -> Self:
        # Draft documents intentionally allow an empty media/case/CTA block.
        # The editor can then persist a newly added module immediately instead
        # of losing it while the user is still choosing assets or content.
        # Publishing performs the stricter completeness check.
        if len(set(self.faq_document_ids)) != len(self.faq_document_ids):
            raise ValueError("faq document ids must be unique")
        if len({item.id for item in self.action_items}) != len(self.action_items):
            raise ValueError("action item ids must be unique")
        if len({item.id for item in self.gallery_items}) != len(self.gallery_items):
            raise ValueError("gallery item ids must be unique")
        if len({item.id for item in self.product_overrides}) != len(self.product_overrides):
            raise ValueError("product override ids must be unique")
        if len({item.id for item in self.case_overrides}) != len(self.case_overrides):
            raise ValueError("case override ids must be unique")
        if self.type != "image_gallery" and self.gallery_items:
            raise ValueError("gallery_items are only valid for image_gallery blocks")
        if self.type != "business_collection" and self.product_overrides:
            raise ValueError("product_overrides are only valid for business_collection blocks")
        if self.type != "case_collection" and self.case_overrides:
            raise ValueError("case_overrides are only valid for case_collection blocks")
        if any(item.id not in self.product_ids for item in self.product_overrides):
            raise ValueError("product override ids must be selected product ids")
        if any(item.id not in self.case_ids for item in self.case_overrides):
            raise ValueError("case override ids must be selected case ids")
        if self.type == "faq":
            self.faq_mode = self.faq_mode or "all_published"
            # Legacy editor versions stored a manual answer here. FAQ is now
            # data-bound, so parsing a compatible document deliberately drops
            # that duplicate copy instead of exposing stale content.
            self.body = None
            if self.faq_mode == "all_published":
                self.faq_document_ids = []
        elif self.faq_mode is not None or self.faq_document_ids:
            raise ValueError("faq selection fields are only valid for faq blocks")
        if self.type != "action_collection" and self.action_items:
            raise ValueError("action_items are only valid for action_collection blocks")
        if self.type == "action_collection":
            self.action_template = self.action_template or "shortcuts"
        elif self.action_template is not None:
            raise ValueError("action_template is only valid for action_collection blocks")
        if self.type != "identity" and self.presentation is not None:
            raise ValueError("presentation is only valid for identity blocks")
        return self


class EnterpriseTemplateDocument(CatalogStrictModel):
    schema_version: Literal[1] = 1
    theme_key: Literal["brand", "clean", "warm"] = "brand"
    blocks: list[EnterpriseTemplateBlock] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def validate_unique_block_ids(self) -> Self:
        if len({block.id for block in self.blocks}) != len(self.blocks):
            raise ValueError("enterprise template block ids must be unique")
        if len({block.sort_order for block in self.blocks}) != len(self.blocks):
            raise ValueError("enterprise template block sort orders must be unique")
        identity_blocks = [block for block in self.blocks if block.type == "identity"]
        if len(identity_blocks) != 1:
            raise ValueError("enterprise template must contain exactly one identity block")
        if not identity_blocks[0].visible:
            raise ValueError("identity block must remain visible")
        self.blocks.sort(key=lambda block: block.sort_order)
        return self


class CreateCardRequest(CardWriteFields):
    card_kind: CardKindValue = "employee"
    owner_user_id: uuid.UUID | None = None
    template_source_card_id: uuid.UUID | None = None
    template_document: EnterpriseTemplateDocument | None = None

    @model_validator(mode="after")
    def validate_card_identity(self) -> Self:
        if self.card_kind == "enterprise" and self.owner_user_id is not None:
            raise ValueError("enterprise cards must not have an employee owner")
        if self.template_source_card_id is not None and self.template_document is not None:
            raise ValueError("template source card and template document are mutually exclusive")
        return self


class EnterpriseTemplateRecord(CatalogStrictModel):
    card_id: uuid.UUID
    version: int = Field(ge=1)
    draft: EnterpriseTemplateDocument
    published: EnterpriseTemplateDocument | None = None


class EnterpriseTemplateEnvelope(CatalogStrictModel):
    data: EnterpriseTemplateRecord


class UpdateEnterpriseTemplateRequest(EnterpriseTemplateDocument):
    pass


class CardComposerDefaultRecord(CatalogStrictModel):
    """Company-owned default free-module configuration for one card kind."""

    card_kind: CardKindValue
    version: int = Field(ge=1)
    document: EnterpriseTemplateDocument


class CardComposerDefaultEnvelope(CatalogStrictModel):
    data: CardComposerDefaultRecord


class UpdateCardComposerDefaultRequest(EnterpriseTemplateDocument):
    pass


class ManagedCardRecord(CardWriteFields):
    id: uuid.UUID
    card_kind: CardKindValue
    owner_user_id: uuid.UUID | None = None
    slug: str
    status: ContentStatusValue
    published_at: datetime | None = None
    version: int = Field(ge=1)
    share_url: str
    qr_url: str = Field(description="The public URL that should be encoded into a QR code")
    created_at: datetime
    updated_at: datetime


class ManagedCardEnvelope(CatalogStrictModel):
    data: ManagedCardRecord


class ManagedCardListEnvelope(CatalogStrictModel):
    data: list[ManagedCardRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


__all__ = [
    "CaseStudyEnvelope",
    "CaseStudyListEnvelope",
    "CaseStudyRecord",
    "CreateCardRequest",
    "CreateCaseStudyRequest",
    "CreateForbiddenTopicRequest",
    "CreateProductRequest",
    "ForbiddenTopicEnvelope",
    "ForbiddenTopicListEnvelope",
    "ForbiddenTopicRecord",
    "ManagedCardEnvelope",
    "ManagedCardListEnvelope",
    "ManagedCardRecord",
    "EnterpriseTemplateActionItem",
    "EnterpriseTemplateBackground",
    "EnterpriseTemplateBlock",
    "EnterpriseTemplateDocument",
    "EnterpriseTemplateCaseItem",
    "EnterpriseTemplateEnvelope",
    "EnterpriseTemplatePresentation",
    "EnterpriseTemplateRecord",
    "ProductEnvelope",
    "ProductListEnvelope",
    "ProductRecord",
    "PublicCaseStudyEnvelope",
    "PublicCaseStudyListEnvelope",
    "PublicCaseStudyRecord",
    "PublicProductEnvelope",
    "PublicProductListEnvelope",
    "PublicProductRecord",
    "UpdateCaseStudyRequest",
    "UpdateForbiddenTopicRequest",
    "UpdateManagedCardRequest",
    "UpdateEnterpriseTemplateRequest",
    "UpdateProductRequest",
    "validate_safe_asset_url",
]
