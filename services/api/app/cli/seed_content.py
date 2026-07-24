from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry
from app.core.config import Settings, get_settings
from app.core.pii import PiiCipher
from app.core.staff_auth import hash_staff_password, normalize_staff_account
from app.core.text_integrity import ensure_text_tree
from app.db.models import (
    Card,
    CardContactField,
    CaseStudy,
    Company,
    ContentStatus,
    ForbiddenTopic,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeVersion,
    LifecycleStatus,
    Membership,
    MembershipRole,
    ModelConfig,
    Product,
    PromptStatus,
    PromptVersion,
    ReviewStatus,
    StaffCredential,
    Tenant,
    TenantType,
    User,
    Visibility,
)

_SEED_NAMESPACE = uuid.UUID("f2a9d459-8e1b-49fb-94ee-33fc5125deaf")


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*")
    @classmethod
    def reject_broken_text_encoding(cls, value: Any) -> Any:
        return ensure_text_tree(value)


class TenantInput(StrictInput):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=200)
    type: str


class CompanyInput(StrictInput):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=120)


class CardInput(StrictInput):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$")
    status: Literal["published"]


class DocumentInput(StrictInput):
    external_id: str = Field(min_length=1, max_length=160)
    source_type: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=500)
    visibility: Literal["public", "authenticated", "internal"]
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContactFieldInput(StrictInput):
    field_type: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2_000)
    visibility: Literal["public", "authenticated", "internal"] = "public"
    sort_order: int = Field(default=0, ge=0)


class ProductInput(StrictInput):
    external_id: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$")
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    summary: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    audience: str | None = None
    price_boundary: str | None = None
    image_url: str | None = Field(default=None, max_length=2_048)
    sort_order: int = Field(default=0, ge=0)
    settings: dict[str, Any] = Field(default_factory=dict)


class CaseStudyInput(StrictInput):
    external_id: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,94}[a-z0-9]$")
    title: str = Field(min_length=1, max_length=240)
    industry: str | None = Field(default=None, max_length=120)
    background: str = Field(min_length=1)
    solution: str = Field(min_length=1)
    result: str = Field(min_length=1)
    client_display_name: str | None = Field(default=None, max_length=200)
    image_url: str | None = Field(default=None, max_length=2_048)
    sort_order: int = Field(default=0, ge=0)
    settings: dict[str, Any] = Field(default_factory=dict)


class ForbiddenTopicInput(StrictInput):
    external_id: str = Field(min_length=1, max_length=160)
    topic: str = Field(min_length=1, max_length=240)
    match_terms: list[str] = Field(default_factory=list, max_length=64)
    action: Literal["refuse", "handoff", "safe_template"] = "refuse"
    safe_response: str | None = Field(default=None, max_length=5_000)


class ContentPackage(StrictInput):
    schema_version: Literal["1.0"]
    tenant: TenantInput
    company: CompanyInput
    card: CardInput
    knowledge_version: str = Field(min_length=1, max_length=80)
    knowledge_sequence: int = Field(default=1, ge=1)
    documents: list[DocumentInput] = Field(min_length=1)
    contact_fields: list[ContactFieldInput] = Field(default_factory=list)
    products: list[ProductInput] = Field(default_factory=list)
    case_studies: list[CaseStudyInput] = Field(default_factory=list)
    forbidden_topics: list[ForbiddenTopicInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope_and_documents(self) -> "ContentPackage":
        if self.company.slug != self.card.slug or self.tenant.slug != self.company.slug:
            raise ValueError("tenant, company and card slugs must match in a seed package")
        external_ids = [document.external_id for document in self.documents]
        if len(set(external_ids)) != len(external_ids):
            raise ValueError("document external_id values must be unique")
        for label, values in (
            ("product", [item.external_id for item in self.products]),
            ("case study", [item.external_id for item in self.case_studies]),
            ("forbidden topic", [item.external_id for item in self.forbidden_topics]),
            ("contact field", [item.field_type for item in self.contact_fields]),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{label} identifiers must be unique")
        return self


def load_content_package(path: Path) -> ContentPackage:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ContentPackage.model_validate(payload)


def deterministic_id(slug: str, kind: str, value: str = "root") -> uuid.UUID:
    return uuid.uuid5(_SEED_NAMESPACE, f"{slug}:{kind}:{value}")


def should_activate_seed_version(
    current_version_id: uuid.UUID | None,
    seed_version_id: uuid.UUID,
    *,
    current_is_seed: bool = False,
) -> bool:
    """Keep startup seeding from rolling back an administrator publication."""

    return (
        current_version_id is None
        or current_version_id == seed_version_id
        or current_is_seed
    )


def seed_owned_version_requires_activation(
    metadata: Any,
    *,
    slug: str,
    seed_version_id: uuid.UUID,
) -> bool:
    """Replace old seed content but preserve an index derived from this seed."""

    if not isinstance(metadata, dict) or metadata.get("seed_package") != slug:
        return False
    embedding_index = metadata.get("embedding_index")
    return not (
        isinstance(embedding_index, dict)
        and embedding_index.get("source_version_id") == str(seed_version_id)
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _should_bootstrap_staff(settings: Settings, slug: str) -> bool:
    return settings.admin_bootstrap_tenant_slug == slug


async def seed_package(
    session: AsyncSession,
    package: ContentPackage,
    settings: Settings,
) -> None:
    now = datetime.now(UTC)
    slug = package.card.slug
    tenant_id = deterministic_id(slug, "tenant")
    company_id = deterministic_id(slug, "company")
    owner_id = deterministic_id(slug, "owner")
    membership_id = deterministic_id(slug, "membership")
    card_id = deterministic_id(slug, "card")
    prompt_id = deterministic_id(slug, "prompt", DEFAULT_PROMPT_VERSION)
    model_config_id = deterministic_id(slug, "model", settings.llm_provider)

    await session.execute(
        text(
            """
            SELECT
                set_config('app.tenant_id', :tenant_id, true),
                set_config('app.company_id', :company_id, true),
                set_config('app.card_slug', :card_slug, true)
            """
        ),
        {
            "tenant_id": str(tenant_id),
            "company_id": str(company_id),
            "card_slug": slug,
        },
    )

    await session.execute(
        pg_insert(Tenant)
        .values(
            id=tenant_id,
            slug=slug,
            name=package.tenant.name,
            type=TenantType.ENTERPRISE,
            status=LifecycleStatus.ACTIVE,
            settings={"seed_slug": slug, "schema_version": package.schema_version},
        )
        .on_conflict_do_nothing(index_elements=[Tenant.id])
    )
    await session.execute(
        pg_insert(Company)
        .values(
            id=company_id,
            tenant_id=tenant_id,
            name=package.company.name,
            normalized_name=package.company.name.casefold(),
            industry=package.company.industry,
            status=LifecycleStatus.ACTIVE,
            settings={
                "seed_slug": slug,
                "summary": package.documents[0].content,
                "policy_versions": {
                    "profile_personalization": "profile-personalization-2026.07-v1"
                },
            },
        )
        .on_conflict_do_nothing(index_elements=[Company.id])
    )
    await session.execute(
        pg_insert(User)
        .values(
            id=owner_id,
            display_name=f"{package.company.name} 内容管理员",
            status=LifecycleStatus.ACTIVE,
        )
        .on_conflict_do_nothing(index_elements=[User.id])
    )
    await session.execute(
        pg_insert(Membership)
        .values(
            id=membership_id,
            user_id=owner_id,
            tenant_id=tenant_id,
            company_id=company_id,
            role=MembershipRole.COMPANY_ADMIN,
            permissions=["knowledge.review", "card.publish"],
            status=LifecycleStatus.ACTIVE,
        )
        .on_conflict_do_nothing(index_elements=[Membership.id])
    )
    if _should_bootstrap_staff(settings, slug):
        if settings.admin_bootstrap_account is None or settings.admin_bootstrap_password is None:
            raise ValueError("admin bootstrap settings are incomplete")
        credential_id = deterministic_id(slug, "staff-credential", "bootstrap")
        await session.execute(
            pg_insert(StaffCredential)
            .values(
                id=credential_id,
                user_id=owner_id,
                membership_id=membership_id,
                tenant_id=tenant_id,
                company_id=company_id,
                account_normalized=normalize_staff_account(settings.admin_bootstrap_account),
                password_hash=hash_staff_password(
                    settings.admin_bootstrap_password.get_secret_value()
                ),
                is_enabled=True,
                failed_attempts=0,
                password_changed_at=now,
            )
            .on_conflict_do_nothing()
        )
    questions = [document.title for document in package.documents[:3]]
    await session.execute(
        pg_insert(Card)
        .values(
            id=card_id,
            tenant_id=tenant_id,
            company_id=company_id,
            card_kind="enterprise",
            owner_user_id=None,
            responsible_user_id=owner_id,
            slug=slug,
            display_name=package.company.name,
            status=ContentStatus.PUBLISHED,
            published_at=now,
            settings={
                "title": package.company.name,
                "assistant_name": f"{package.company.name} AI 助手",
                "welcome_message": "你好，我可以根据已发布的企业资料回答问题。",
                "suggested_questions": questions,
                "policy_versions": {
                    "privacy": "privacy-2026.07-v1",
                    "chat_notice": "chat-notice-2026.07-v1",
                    "lead_consent": "lead-consent-2026.07-v1",
                    "profile_personalization": "profile-personalization-2026.07-v1",
                },
            },
        )
        .on_conflict_do_update(
            index_elements=[Card.id],
            set_={
                "card_kind": "enterprise",
                "owner_user_id": None,
                "responsible_user_id": owner_id,
            },
        )
    )

    cipher = PiiCipher.from_settings(settings)
    for contact in package.contact_fields:
        contact_id = deterministic_id(slug, "contact-field", contact.field_type)
        await session.execute(
            pg_insert(CardContactField)
            .values(
                id=contact_id,
                tenant_id=tenant_id,
                company_id=company_id,
                card_id=card_id,
                field_type=contact.field_type,
                label=contact.label,
                value_ciphertext=cipher.encrypt(contact.value),
                value_hmac=cipher.hmac(contact.value),
                visibility=Visibility(contact.visibility),
                sort_order=contact.sort_order,
                is_active=True,
                encryption_key_ref=cipher.key_ref,
            )
            .on_conflict_do_nothing(index_elements=[CardContactField.id])
        )

    for item in package.products:
        product_id = deterministic_id(slug, "product", item.external_id)
        await session.execute(
            pg_insert(Product)
            .values(
                id=product_id,
                tenant_id=tenant_id,
                company_id=company_id,
                slug=item.slug,
                name=item.name,
                category=item.category,
                summary=item.summary,
                detail=item.detail,
                audience=item.audience,
                price_boundary=item.price_boundary,
                image_url=item.image_url,
                visibility=Visibility.PUBLIC,
                status=ContentStatus.PUBLISHED,
                published_at=now,
                sort_order=item.sort_order,
                settings=item.settings,
            )
            .on_conflict_do_nothing(index_elements=[Product.id])
        )

    for item in package.case_studies:
        case_id = deterministic_id(slug, "case-study", item.external_id)
        await session.execute(
            pg_insert(CaseStudy)
            .values(
                id=case_id,
                tenant_id=tenant_id,
                company_id=company_id,
                slug=item.slug,
                title=item.title,
                industry=item.industry,
                background=item.background,
                solution=item.solution,
                result=item.result,
                client_display_name=item.client_display_name,
                image_url=item.image_url,
                visibility=Visibility.PUBLIC,
                status=ContentStatus.PUBLISHED,
                published_at=now,
                sort_order=item.sort_order,
                settings=item.settings,
            )
            .on_conflict_do_nothing(index_elements=[CaseStudy.id])
        )

    for item in package.forbidden_topics:
        topic_id = deterministic_id(slug, "forbidden-topic", item.external_id)
        await session.execute(
            pg_insert(ForbiddenTopic)
            .values(
                id=topic_id,
                tenant_id=tenant_id,
                company_id=company_id,
                topic=item.topic,
                match_terms=item.match_terms,
                action=item.action,
                safe_response=item.safe_response,
                is_active=True,
            )
            .on_conflict_do_nothing(index_elements=[ForbiddenTopic.id])
        )

    prompt = PromptRegistry().get(DEFAULT_PROMPT_VERSION)
    prompt_hash = _sha256(prompt.system_text)
    await session.execute(
        pg_insert(PromptVersion)
        .values(
            id=prompt_id,
            tenant_id=tenant_id,
            company_id=company_id,
            name=DEFAULT_PROMPT_VERSION,
            purpose="rag_answer",
            version_number=1,
            content=prompt.system_text,
            content_hash=prompt_hash,
            change_summary="Grounded enterprise answers with open general chat",
            evaluation_result={"status": "requires_pilot_evaluation"},
            status=PromptStatus.PUBLISHED,
            published_by=owner_id,
            published_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_prompt_versions_name_version")
    )
    persisted_prompt = (
        await session.execute(
            select(PromptVersion.purpose, PromptVersion.content_hash).where(
                PromptVersion.tenant_id == tenant_id,
                PromptVersion.company_id == company_id,
                PromptVersion.name == DEFAULT_PROMPT_VERSION,
                PromptVersion.version_number == 1,
            )
        )
    ).one()
    if (
        persisted_prompt.purpose != "rag_answer"
        or persisted_prompt.content_hash != prompt_hash
    ):
        raise ValueError(
            f"immutable prompt version changed for {DEFAULT_PROMPT_VERSION}; "
            "publish a new prompt version"
        )
    await session.execute(
        pg_insert(ModelConfig)
        .values(
            id=model_config_id,
            tenant_id=tenant_id,
            company_id=company_id,
            purpose="chat",
            provider=settings.llm_provider,
            model_name=settings.llm_model,
            endpoint_region=None,
            secret_ref="env:LLM_API_KEY",  # noqa: S106 - reference, never a secret value
            timeout_ms=round(settings.llm_timeout_seconds * 1_000),
            max_retries=2,
            max_concurrency=settings.llm_max_concurrency,
            daily_budget_cny=Decimal(str(settings.model_daily_budget_cny)),
            data_retention="no_training",
            enabled=True,
            parameters={
                "thinking": settings.llm_thinking,
                "temperature": settings.llm_temperature,
                "max_tokens": settings.llm_max_output_tokens,
            },
        )
        .on_conflict_do_update(
            constraint="uq_model_configs_purpose_provider",
            set_={
                "model_name": settings.llm_model,
                "timeout_ms": round(settings.llm_timeout_seconds * 1_000),
                "max_concurrency": settings.llm_max_concurrency,
                "daily_budget_cny": Decimal(str(settings.model_daily_budget_cny)),
                "enabled": True,
            },
        )
    )

    for document in package.documents:
        document_id = deterministic_id(slug, "document", document.external_id)
        version_id = deterministic_id(
            slug,
            "knowledge-version",
            f"{document.external_id}:{package.knowledge_version}",
        )
        chunk_id = deterministic_id(slug, "chunk", f"{version_id}:0")
        content_hash = _sha256(document.content)
        await session.execute(
            pg_insert(KnowledgeDocument)
            .values(
                id=document_id,
                tenant_id=tenant_id,
                company_id=company_id,
                source_type=document.source_type,
                source_id=document.external_id,
                title=document.title,
                # A document cannot be published until its approved version and
                # indexed chunks exist.  Insert new documents as drafts, build
                # the immutable version/chunk records below, then activate them
                # with the final update in this transaction.
                status=ContentStatus.DRAFT,
                current_version_id=None,
            )
            .on_conflict_do_nothing(index_elements=[KnowledgeDocument.id])
        )
        await session.execute(
            pg_insert(KnowledgeVersion)
            .values(
                id=version_id,
                tenant_id=tenant_id,
                company_id=company_id,
                document_id=document_id,
                version_number=package.knowledge_sequence,
                raw_text=document.content,
                content_hash=content_hash,
                review_status=ReviewStatus.APPROVED,
                reviewed_by=owner_id,
                reviewed_at=now,
                published_at=now,
            )
            .on_conflict_do_nothing(index_elements=[KnowledgeVersion.id])
        )
        existing_hash = (
            await session.execute(
                select(KnowledgeVersion.content_hash).where(KnowledgeVersion.id == version_id)
            )
        ).scalar_one()
        if existing_hash != content_hash:
            raise ValueError(
                f"immutable knowledge version changed for {document.external_id}; "
                "bump knowledge_version and knowledge_sequence"
            )
        await session.execute(
            pg_insert(KnowledgeChunk.__table__)
            .values(
                id=chunk_id,
                tenant_id=tenant_id,
                company_id=company_id,
                document_id=document_id,
                version_id=version_id,
                ordinal=0,
                title=document.title,
                text=document.content,
                token_count=max(1, len(document.content) // 2),
                embedding=None,
                embedding_model=None,
                visibility=Visibility(document.visibility),
                is_active=False,
                source_type=document.source_type,
                source_id=document.external_id,
                content_hash=content_hash,
                metadata={
                    **document.metadata,
                    "seed_package": slug,
                    "knowledge_version": package.knowledge_version,
                },
            )
            .on_conflict_do_nothing(index_elements=[KnowledgeChunk.__table__.c.id])
        )
        current_version_id = await session.scalar(
            select(KnowledgeDocument.current_version_id)
            .where(KnowledgeDocument.id == document_id)
            .with_for_update()
        )
        current_chunk_metadata = None
        if current_version_id is not None:
            current_chunk_metadata = await session.scalar(
                select(KnowledgeChunk.metadata_json)
                .where(
                    KnowledgeChunk.document_id == document_id,
                    KnowledgeChunk.version_id == current_version_id,
                    KnowledgeChunk.is_active.is_(True),
                )
                .limit(1)
            )
        current_is_seed = seed_owned_version_requires_activation(
            current_chunk_metadata,
            slug=slug,
            seed_version_id=version_id,
        )
        if should_activate_seed_version(
            current_version_id,
            version_id,
            current_is_seed=current_is_seed,
        ):
            await session.execute(
                update(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id == document_id,
                    KnowledgeChunk.version_id != version_id,
                )
                .values(is_active=False)
            )
            await session.execute(
                update(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id == document_id,
                    KnowledgeChunk.version_id == version_id,
                )
                .values(is_active=True)
            )
            await session.execute(
                update(KnowledgeDocument)
                .where(KnowledgeDocument.id == document_id)
                .values(current_version_id=version_id, status=ContentStatus.PUBLISHED)
            )


async def seed_paths(paths: list[Path], settings: Settings) -> None:
    packages = [(path, load_content_package(path)) for path in paths]
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for path, package in packages:
            async with sessions() as session, session.begin():
                await seed_package(session, package, settings)
            print(f"seeded {package.card.slug} from {path}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and seed enterprise content packages")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    asyncio.run(seed_paths(args.paths, get_settings()))


if __name__ == "__main__":
    main()
