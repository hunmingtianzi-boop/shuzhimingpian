from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.api.catalog_schemas import CardContactItem, EnterpriseTemplateDocument
from app.api.errors import ApiError
from app.db.models import Card, CardKind, Company, ContentStatus, LifecycleStatus
from app.services.catalog_store import (
    CatalogScope,
    CatalogStore,
    _merge_default_template_blocks,
    _require_complete_template_blocks,
)
from app.services.public_store import (
    _public_enterprise_identity,
    _public_enterprise_template,
)


def _asset_url(company_id: uuid.UUID) -> str:
    return f"/api/v1/public/card-assets/{company_id}/{uuid.uuid4()}.webp"


class _Rows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


def _identity(*, company_id: uuid.UUID | None = None) -> dict[str, object]:
    background = (
        {
            "asset_url": _asset_url(company_id),
            "fit": "cover",
            "position": "center",
            "scale": 1.15,
            "opacity": 0.72,
            "overlay": "brand",
        }
        if company_id is not None
        else None
    )
    return {
        "id": "identity",
        "type": "identity",
        "sort_order": 0,
        "layout_variant": "horizontal",
        "presentation": {
            "identity_layout": "horizontal",
            "background": background,
        },
    }


def test_explicit_template_delete_is_preserved_but_identity_is_repaired() -> None:
    explicit = _merge_default_template_blocks(
        [
            {"id": "intro", "type": "rich_text", "sort_order": 0},
            {
                "id": "identity",
                "type": "identity",
                "visible": False,
                "sort_order": 1,
            },
        ]
    )

    assert [block["id"] for block in explicit] == ["intro", "identity"]
    assert explicit[1]["visible"] is True
    assert [block["sort_order"] for block in explicit] == [0, 1]


def test_empty_legacy_template_still_receives_compatibility_defaults() -> None:
    blocks = _merge_default_template_blocks([])

    assert [block["id"] for block in blocks] == [
        "identity",
        "overview",
        "intro",
        "business",
        "cases",
        "trust",
        "faq",
        "ai",
    ]


def test_additive_v1_presentation_layout_and_actions_round_trip() -> None:
    company_id = uuid.uuid4()
    document = EnterpriseTemplateDocument.model_validate(
        {
            "schema_version": 1,
            "blocks": [
                _identity(company_id=company_id),
                {
                    "id": "actions",
                    "type": "action_collection",
                    "sort_order": 1,
                    "layout_variant": "grid",
                    "item_limit": 4,
                    "action_items": [
                        {
                            "id": "conference",
                            "title": "世界会展大会",
                            "summary": "查看大会详情",
                            "label": "查看详情",
                            "image_url": _asset_url(company_id),
                            "target_type": "external_url",
                            "target_value": "https://events.example.com/conference",
                            "open_mode": "new_tab",
                        },
                        {
                            "id": "products",
                            "title": "产品中心",
                            "target_type": "internal_path",
                            "target_value": "/products?from=card",
                        },
                        {
                            "id": "phone",
                            "title": "电话咨询",
                            "target_type": "phone",
                            "target_value": "+86 400-888-8888",
                        },
                    ],
                },
            ],
        }
    )

    assert document.schema_version == 1
    assert document.blocks[0].presentation is not None
    assert document.blocks[0].presentation.background is not None
    assert document.blocks[0].presentation.background.opacity == 0.72
    assert document.blocks[1].layout_variant == "grid"
    assert [item.target_type for item in document.blocks[1].action_items] == [
        "external_url",
        "internal_path",
        "phone",
    ]


def test_gallery_items_and_real_content_overrides_round_trip() -> None:
    company_id = uuid.uuid4()
    product_id = uuid.uuid4()
    case_id = uuid.uuid4()
    document = EnterpriseTemplateDocument.model_validate(
        {
            "schema_version": 1,
            "blocks": [
                _identity(),
                {
                    "id": "business",
                    "type": "business_collection",
                    "sort_order": 1,
                    "product_ids": [product_id],
                    "product_overrides": [
                        {"id": product_id, "title": "名片展示标题"}
                    ],
                },
                {
                    "id": "cases",
                    "type": "case_collection",
                    "sort_order": 2,
                    "case_ids": [case_id],
                    "case_overrides": [
                        {
                            "id": case_id,
                            "result": "增长 68%",
                            "metrics": [{"value": "+68%", "label": "转化提升"}],
                        }
                    ],
                },
                {
                    "id": "gallery",
                    "type": "image_gallery",
                    "sort_order": 3,
                    "gallery_items": [
                        {
                            "id": "launch",
                            "image_url": _asset_url(company_id),
                            "title": "项目启动",
                            "time_label": "2026.08",
                            "badge_mode": "time",
                        }
                    ],
                },
            ],
        }
    )

    assert document.blocks[1].product_overrides[0].title == "名片展示标题"
    assert document.blocks[2].case_overrides[0].metrics[0].value == "+68%"
    assert document.blocks[3].gallery_items[0].badge_mode == "time"


@pytest.mark.parametrize(
    ("target_type", "target_value"),
    [
        ("external_url", "http://example.com"),
        ("external_url", "https://127.0.0.1/admin"),
        ("internal_path", "//attacker.example/path"),
        ("internal_path", "/cards/../admin"),
        ("phone", "javascript:alert(1)"),
        ("map", "file:///etc/passwd"),
    ],
)
def test_unsafe_action_targets_are_rejected(target_type: str, target_value: str) -> None:
    with pytest.raises(ValidationError):
        EnterpriseTemplateDocument.model_validate(
            {
                "blocks": [
                    _identity(),
                    {
                        "id": "actions",
                        "type": "action_collection",
                        "sort_order": 1,
                        "action_items": [
                            {
                                "id": "unsafe",
                                "title": "不安全入口",
                                "target_type": target_type,
                                "target_value": target_value,
                            }
                        ],
                    },
                ]
            }
        )


@pytest.mark.asyncio
async def test_cross_tenant_presentation_asset_is_rejected_before_publish() -> None:
    company_id = uuid.uuid4()
    document = EnterpriseTemplateDocument.model_validate(
        {"blocks": [_identity(company_id=uuid.uuid4())]}
    )
    store = object.__new__(CatalogStore)

    with pytest.raises(ApiError) as error:
        await store._validate_enterprise_template_resources(
            AsyncMock(),
            scope=CatalogScope(
                tenant_id=uuid.uuid4(),
                company_id=company_id,
                actor_user_id=uuid.uuid4(),
                role="company_admin",
            ),
            document=document,
            require_public_cases=False,
        )

    assert error.value.code == "TEMPLATE_ASSET_OUT_OF_SCOPE"


@pytest.mark.asyncio
async def test_cross_tenant_or_unpublished_product_reference_is_rejected() -> None:
    product_id = uuid.uuid4()
    document = EnterpriseTemplateDocument.model_validate(
        {
            "blocks": [
                _identity(),
                {
                    "id": "business",
                    "type": "business_collection",
                    "sort_order": 1,
                    "product_ids": [str(product_id)],
                },
            ]
        }
    )
    session = AsyncMock()
    session.scalars.return_value = _Rows([])
    store = object.__new__(CatalogStore)

    with pytest.raises(ApiError) as error:
        await store._validate_enterprise_template_resources(
            session,
            scope=CatalogScope(
                tenant_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                actor_user_id=uuid.uuid4(),
                role="company_admin",
            ),
            document=document,
            require_public_cases=True,
        )

    assert error.value.code == "TEMPLATE_PRODUCT_OUT_OF_SCOPE"


@pytest.mark.asyncio
async def test_same_company_product_reference_is_projected_from_server_data() -> None:
    product_id = uuid.uuid4()
    product = SimpleNamespace(
        id=product_id,
        slug="trusted-product",
        name="真实产品",
        category="企业服务",
        summary="来自服务端的数据",
        image_url=None,
    )
    document = EnterpriseTemplateDocument.model_validate(
        {
            "blocks": [
                _identity(),
                {
                    "id": "business",
                    "type": "business_collection",
                    "sort_order": 1,
                    "product_ids": [str(product_id)],
                },
            ]
        }
    )
    session = AsyncMock()
    session.scalars.return_value = _Rows([product])
    store = object.__new__(CatalogStore)

    projected = await store._validate_enterprise_template_resources(
        session,
        scope=CatalogScope(
            tenant_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            actor_user_id=uuid.uuid4(),
            role="company_admin",
        ),
        document=document,
        require_public_cases=True,
    )

    assert projected.blocks[1].product_items[0].id == product_id
    assert projected.blocks[1].product_items[0].name == "真实产品"


@pytest.mark.asyncio
async def test_public_projection_keeps_action_config_and_identity_presentation() -> None:
    company_id = uuid.uuid4()
    projection = await _public_enterprise_template(
        AsyncMock(),
        tenant_id=uuid.uuid4(),
        company_id=company_id,
        value={
            "schema_version": 1,
            "blocks": [
                _identity(company_id=company_id),
                {
                    "id": "actions",
                    "type": "action_collection",
                    "sort_order": 1,
                    "layout_variant": "featured",
                    "item_limit": 1,
                    "action_items": [
                        {
                            "id": "website",
                            "title": "企业官网",
                            "target_type": "external_url",
                            "target_value": "https://example.com",
                            "open_mode": "new_tab",
                        }
                    ],
                },
            ],
        },
    )

    assert projection is not None
    assert [block["id"] for block in projection["blocks"]] == ["identity", "actions"]
    assert projection["blocks"][0]["presentation"]["background"]["overlay"] == "brand"
    assert projection["blocks"][1]["layout_variant"] == "featured"
    assert projection["blocks"][1]["action_items"][0]["target_type"] == "external_url"


@pytest.mark.asyncio
async def test_default_collections_project_all_published_company_content() -> None:
    tenant_id = uuid.uuid4()
    company_id = uuid.uuid4()
    product_id = uuid.uuid4()
    case_id = uuid.uuid4()
    session = AsyncMock()
    session.scalars.side_effect = [
        _Rows(
            [
                SimpleNamespace(
                    id=product_id,
                    slug="ai-card",
                    name="企业 AI 数智名片",
                    category="AI 企业服务",
                    summary="把企业身份、资料与服务放进统一入口。",
                    image_url=None,
                )
            ]
        ),
        _Rows(
            [
                SimpleNamespace(
                    id=case_id,
                    slug="retail-growth",
                    title="零售增长案例",
                    industry="零售业",
                    client_display_name="某连锁企业",
                    background="客户需要统一业务入口。",
                    solution="搭建可分享的员工名片。",
                    result="咨询转化提升 68%",
                    image_url=None,
                )
            ]
        ),
    ]

    projection = await _public_enterprise_template(
        session,
        tenant_id=tenant_id,
        company_id=company_id,
        value={
            "schema_version": 1,
            "blocks": [
                _identity(),
                {
                    "id": "business",
                    "type": "business_collection",
                    "sort_order": 1,
                    "product_ids": [],
                },
                {
                    "id": "cases",
                    "type": "case_collection",
                    "sort_order": 2,
                    "case_ids": [],
                },
                {
                    "id": "custom-business",
                    "type": "business_collection",
                    "sort_order": 3,
                    "product_ids": [],
                },
            ],
        },
    )

    assert projection is not None
    assert projection["blocks"][1]["product_ids"] == [str(product_id)]
    assert projection["blocks"][1]["product_items"][0]["name"] == "企业 AI 数智名片"
    assert projection["blocks"][2]["case_ids"] == [str(case_id)]
    assert projection["blocks"][2]["case_items"][0]["result"] == "咨询转化提升 68%"
    assert projection["blocks"][3]["product_items"] == []


def test_enterprise_identity_prefers_company_profile_and_falls_back_to_legacy_card() -> None:
    company = Company(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="真实企业名称",
        normalized_name="真实企业名称",
        industry="企业服务",
        status=LifecycleStatus.ACTIVE,
        settings={
            "summary": "企业资料摘要",
            "logo_url": "https://cdn.example.com/company.webp",
            "business_positioning": "可信赖的企业增长伙伴",
        },
        version=1,
    )
    card = Card(
        id=uuid.uuid4(),
        tenant_id=company.tenant_id,
        company_id=company.id,
        card_kind=CardKind.ENTERPRISE,
        owner_user_id=None,
        responsible_user_id=uuid.uuid4(),
        slug="c-" + "a" * 36,
        display_name="旧卡片名称",
        status=ContentStatus.DRAFT,
        settings={
            "title": "旧卡片定位",
            "avatar_url": "https://cdn.example.com/legacy.webp",
            "business_summary": "旧卡片摘要",
        },
        version=1,
    )

    identity = _public_enterprise_identity(card=card, company=company)

    assert identity.display_name == "真实企业名称"
    assert identity.title == "可信赖的企业增长伙伴"
    assert identity.avatar_url == "https://cdn.example.com/company.webp"
    assert identity.business_summary == "企业资料摘要"


def test_action_collection_must_have_at_least_one_item_to_publish() -> None:
    document = EnterpriseTemplateDocument.model_validate(
        {
            "blocks": [
                _identity(),
                {"id": "actions", "type": "action_collection", "sort_order": 1},
            ]
        }
    )

    with pytest.raises(ApiError) as error:
        _require_complete_template_blocks(document)

    assert error.value.code == "TEMPLATE_BLOCK_INCOMPLETE"


def test_identity_contact_item_accepts_real_actions_and_rejects_script_urls() -> None:
    phone = CardContactItem(
        id="work-phone",
        kind="phone",
        label="工作电话",
        value="138 0000 0000",
        href="tel:13800000000",
    )
    address = CardContactItem(
        id="company-address",
        kind="location",
        label="公司地址",
        value="浙江省杭州市",
    )

    assert phone.href == "tel:13800000000"
    assert address.href is None
    with pytest.raises(ValidationError):
        CardContactItem(
            id="unsafe-link",
            kind="website",
            label="危险链接",
            value="点击",
            href="javascript:alert(1)",
        )
