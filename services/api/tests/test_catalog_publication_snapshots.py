from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.models import ContentStatus, Product, Visibility
from app.services.catalog_store import (
    _apply_snapshot,
    _product_record,
    _product_snapshot,
    _public_product_record,
    _publication_impact_reason,
    _publish_catalog_snapshot,
    _with_published_snapshot,
)


def _published_product() -> Product:
    now = datetime.now(UTC)
    return Product(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        slug="enterprise-ai",
        name="已发布名称",
        category="AI",
        summary="已发布摘要",
        detail="已发布详情",
        audience="企业客户",
        price_boundary="按项目报价",
        visibility=Visibility.PUBLIC,
        status=ContentStatus.PUBLISHED,
        published_at=now,
        sort_order=1,
        settings={},
        version=2,
        created_at=now,
        updated_at=now,
    )


def test_public_projection_keeps_published_snapshot_while_admin_edits_draft() -> None:
    product = _published_product()
    snapshot = _product_snapshot(product)
    product.settings = _with_published_snapshot(product.settings, snapshot)
    product.name = "待发布新名称"
    product.summary = "待发布新摘要"

    assert _product_record(product).has_unpublished_changes is True
    public = _public_product_record(product)
    assert public.name == "已发布名称"
    assert public.summary == "已发布摘要"


def test_rollback_snapshot_restores_catalog_fields() -> None:
    product = _published_product()
    snapshot = _product_snapshot(product)
    product.name = "后续版本"
    product.summary = "后续摘要"

    _apply_snapshot(product, snapshot)

    assert product.name == "已发布名称"
    assert product.summary == "已发布摘要"


def test_published_product_can_publish_a_new_snapshot() -> None:
    product = _published_product()
    product.settings = _with_published_snapshot(product.settings, _product_snapshot(product))
    previous_version = product.version
    previous_published_at = product.published_at
    product.summary = "待发布新摘要"

    _publish_catalog_snapshot(product, label="产品", snapshot=_product_snapshot(product))

    assert product.status == ContentStatus.PUBLISHED
    assert product.version == previous_version + 1
    assert product.published_at is not None
    assert product.published_at >= previous_published_at


def test_publication_impact_only_counts_real_template_references() -> None:
    product_id = uuid.uuid4()
    faq_id = uuid.uuid4()
    settings = {
        "enterprise_template_published": {
            "blocks": [
                {"type": "business_collection", "product_ids": [str(product_id)]},
                {"type": "faq", "faq_mode": "all_published", "faq_document_ids": []},
            ]
        }
    }

    assert _publication_impact_reason(
        settings, resource_type="product", resource_key=str(product_id)
    ) == "direct_reference"
    assert _publication_impact_reason(
        settings, resource_type="product", resource_key=str(uuid.uuid4())
    ) is None
    assert _publication_impact_reason(
        settings, resource_type="knowledge_document", resource_key=str(faq_id)
    ) == "all_published"
