from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.api.catalog_schemas import EnterpriseTemplateDocument
from app.db.models import Card, CardKind, ContentStatus
from app.services.catalog_store import (
    _company_card_composer_default,
    _enterprise_template_record,
    _merge_default_template_blocks,
    _publish_card_snapshot,
    card_asset_belongs_to_company,
)
from app.services.public_store import _public_enterprise_template


def _asset_url(company_id: uuid.UUID) -> str:
    return f"/api/v1/public/card-assets/{company_id}/{uuid.uuid4()}.webp"


def test_template_rejects_duplicate_order_and_keeps_incomplete_video_as_draft() -> None:
    with pytest.raises(ValidationError, match="sort orders must be unique"):
        EnterpriseTemplateDocument.model_validate(
            {
                "blocks": [
                    {"id": "identity", "type": "identity", "sort_order": 0},
                    {"id": "one", "type": "rich_text", "sort_order": 1},
                    {"id": "two", "type": "faq", "sort_order": 1},
                ]
            }
        )
    draft = EnterpriseTemplateDocument.model_validate(
        {
            "blocks": [
                {"id": "identity", "type": "identity", "sort_order": 0},
                {
                    "id": "video",
                    "type": "video_link",
                    "sort_order": 1,
                    "video_url": "https://v.qq.com/example",
                },
            ]
        }
    )
    assert draft.blocks[1].video_cover_url is None


def test_template_requires_one_visible_identity_block() -> None:
    with pytest.raises(ValidationError, match="must contain exactly one identity block"):
        EnterpriseTemplateDocument.model_validate(
            {"blocks": [{"id": "intro", "type": "rich_text", "sort_order": 0}]}
        )

    with pytest.raises(ValidationError, match="identity block must remain visible"):
        EnterpriseTemplateDocument.model_validate(
            {
                "blocks": [
                    {
                        "id": "identity",
                        "type": "identity",
                        "visible": False,
                        "sort_order": 0,
                    }
                ]
            }
        )


def test_business_collection_keeps_product_references_without_client_snapshots() -> None:
    product_id = uuid.uuid4()
    document = EnterpriseTemplateDocument.model_validate(
        {
            "blocks": [
                {"id": "identity", "type": "identity", "sort_order": 0},
                {
                    "id": "business",
                    "type": "business_collection",
                    "sort_order": 1,
                    "product_ids": [str(product_id)],
                },
            ]
        }
    )

    assert document.blocks[1].product_ids == [product_id]
    assert document.blocks[1].product_items == []


def test_default_block_compatibility_preserves_an_explicit_page_order() -> None:
    reordered = [
        {
            "id": "custom-intro",
            "type": "rich_text",
            "visible": True,
            "sort_order": 0,
            "title": "企业介绍",
        },
        {
            "id": "identity",
            "type": "identity",
            "visible": False,
            "sort_order": 1,
            "title": "基础名片",
        },
        {
            "id": "business",
            "type": "business_collection",
            "visible": True,
            "sort_order": 2,
            "title": "核心业务",
        },
        {
            "id": "cases",
            "type": "case_collection",
            "visible": True,
            "sort_order": 3,
            "title": "代表案例",
        },
        {
            "id": "custom-overview",
            "type": "rich_text",
            "visible": True,
            "sort_order": 4,
            "title": "概览",
        },
        {
            "id": "trust",
            "type": "trust_panel",
            "visible": True,
            "sort_order": 5,
            "title": "企业资料",
        },
        {"id": "faq", "type": "faq", "visible": True, "sort_order": 6, "title": "常见问题"},
        {
            "id": "ai",
            "type": "ai_assistant",
            "visible": True,
            "sort_order": 7,
            "title": "企业 AI 助手",
        },
    ]

    merged = _merge_default_template_blocks(reordered)

    assert [block["id"] for block in merged] == [
        "custom-intro",
        "identity",
        "business",
        "cases",
        "custom-overview",
        "trust",
        "faq",
        "ai",
    ]
    assert [block["sort_order"] for block in merged] == list(range(8))
    assert merged[1]["visible"] is True
    assert merged[1]["directory_enabled"] is False


def test_uploaded_asset_scope_is_bound_to_company() -> None:
    company_id = uuid.uuid4()
    scoped_path = _asset_url(company_id)
    assert card_asset_belongs_to_company(_asset_url(company_id), company_id)
    assert not card_asset_belongs_to_company(_asset_url(uuid.uuid4()), company_id)
    assert not card_asset_belongs_to_company("https://cdn.example.com/image.webp", company_id)
    assert not card_asset_belongs_to_company(f"https://attacker.example{scoped_path}", company_id)


def test_managed_template_keeps_draft_and_published_snapshots_separate() -> None:
    card = Card(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        card_kind=CardKind.ENTERPRISE,
        owner_user_id=None,
        responsible_user_id=uuid.uuid4(),
        slug="c-" + "a" * 36,
        display_name="示例企业",
        status=ContentStatus.PUBLISHED,
        published_at=datetime.now(UTC),
        settings={
            "enterprise_template_draft": {
                "schema_version": 1,
                "theme_key": "brand",
                "blocks": [{"id": "draft", "type": "rich_text", "sort_order": 0, "body": "草稿"}],
            },
            "enterprise_template_published": {
                "schema_version": 1,
                "theme_key": "brand",
                "blocks": [{"id": "public", "type": "rich_text", "sort_order": 0, "body": "公开"}],
            },
        },
        version=3,
    )
    record = _enterprise_template_record(card)

    assert [block.id for block in record.draft.blocks] == ["identity", "draft"]
    assert record.published is not None
    assert [block.id for block in record.published.blocks] == ["identity", "public"]


def test_employee_card_uses_the_same_free_block_contract_without_copying_identity() -> None:
    card = Card(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        card_kind=CardKind.EMPLOYEE,
        owner_user_id=uuid.uuid4(),
        responsible_user_id=uuid.uuid4(),
        slug="c-" + "e" * 36,
        display_name="员工姓名来自成员资料",
        status=ContentStatus.DRAFT,
        settings={
            "enterprise_template_draft": {
                "schema_version": 1,
                "theme_key": "brand",
                "blocks": [{"id": "intro", "type": "rich_text", "sort_order": 0}],
            }
        },
        version=1,
    )

    record = _enterprise_template_record(card)

    assert [block.id for block in record.draft.blocks] == ["identity", "intro"]
    assert "display_name" not in card.settings


def test_company_default_configuration_is_per_card_kind_with_safe_empty_fallback() -> None:
    document = _company_card_composer_default(
        {
            "card_composer_defaults": {
                "employee": {
                    "schema_version": 1,
                    "theme_key": "clean",
                    "blocks": [
                        {
                            "id": "contact",
                            "type": "cta",
                            "sort_order": 0,
                            "cta_label": "联系我",
                            "cta_url": "https://example.com",
                        }
                    ],
                }
            }
        },
        "employee",
    )

    assert document.theme_key == "clean"
    assert [block.id for block in document.blocks] == ["identity", "contact"]
    assert document.blocks[0].directory_enabled is False
    assert document.blocks[1].cta_label == "联系我"
    assert [block.id for block in _company_card_composer_default({}, "enterprise").blocks] == [
        "identity",
        "overview",
        "intro",
        "business",
        "cases",
        "trust",
        "faq",
        "ai",
    ]


def test_published_card_can_replace_its_public_snapshot() -> None:
    original_published_at = datetime(2026, 1, 1, tzinfo=UTC)
    card = Card(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        card_kind=CardKind.ENTERPRISE,
        owner_user_id=None,
        responsible_user_id=uuid.uuid4(),
        slug="c-" + "b" * 36,
        display_name="示例企业",
        status=ContentStatus.PUBLISHED,
        published_at=original_published_at,
        settings={},
        version=4,
    )

    _publish_card_snapshot(card)

    assert card.status == ContentStatus.PUBLISHED
    assert card.version == 5
    assert card.published_at is not None
    assert card.published_at > original_published_at


@pytest.mark.asyncio
async def test_public_projection_omits_hidden_blocks() -> None:
    company_id = uuid.uuid4()
    projection = await _public_enterprise_template(
        AsyncMock(),
        tenant_id=uuid.uuid4(),
        company_id=company_id,
        value={
            "schema_version": 1,
            "theme_key": "clean",
            "blocks": [
                {"id": "hidden", "type": "rich_text", "visible": False, "sort_order": 0},
                {
                    "id": "public",
                    "type": "rich_text",
                    "visible": True,
                    "sort_order": 1,
                    "body": "公开内容",
                },
                {
                    "id": "spoofed-asset",
                    "type": "image_gallery",
                    "visible": True,
                    "sort_order": 2,
                    "image_urls": [
                        "https://attacker.example/api/v1/public/card-assets/"
                        f"{company_id}/{uuid.uuid4()}.webp"
                    ],
                },
            ],
        },
    )

    assert projection is not None
    assert [block["id"] for block in projection["blocks"]] == ["identity", "public"]
    assert projection["blocks"][0]["directory_enabled"] is False
