from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api.catalog_schemas import CreateCardRequest, EnterpriseTemplateDocument
from app.api.errors import ApiError
from app.db.models import KnowledgeDocument
from app.services.admin_store import AdminScope, AdminStore, selectable_faq_filters
from app.services.catalog_store import (
    CatalogScope,
    CatalogStore,
    _require_complete_template_blocks,
    eligible_faq_document_statement,
)
from app.services.public_store import _public_faq_items


class _Rows:
    def __init__(self, values: list[Any]) -> None:
        self._values = values

    def all(self) -> list[Any]:
        return self._values


def _catalog_scope() -> CatalogScope:
    return CatalogScope(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        role="company_admin",
    )


def _admin_scope() -> AdminScope:
    return AdminScope(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
    )


def _faq_document(
    *, mode: str = "selected", ids: list[uuid.UUID] | None = None
) -> EnterpriseTemplateDocument:
    return EnterpriseTemplateDocument.model_validate(
        {
            "blocks": [
                {"id": "identity", "type": "identity", "sort_order": 0},
                {
                    "id": "faq",
                    "type": "faq",
                    "sort_order": 1,
                    "faq_mode": mode,
                    "faq_document_ids": [str(value) for value in (ids or [])],
                    "body": "旧编辑器手填的答案不得进入模板",
                },
            ]
        }
    )


def _compiled(statement: Any) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_faq_block_defaults_to_live_data_and_discards_legacy_body() -> None:
    selected_id = uuid.uuid4()
    document = _faq_document(mode="all_published", ids=[selected_id])
    block = document.blocks[1]

    assert block.faq_mode == "all_published"
    assert block.faq_document_ids == []
    assert block.body is None


def test_selected_faq_can_be_saved_empty_as_draft_but_cannot_publish() -> None:
    document = _faq_document()

    with pytest.raises(ApiError) as captured:
        _require_complete_template_blocks(document)

    assert captured.value.code == "TEMPLATE_BLOCK_INCOMPLETE"
    assert captured.value.details == {"block_ids": ["faq"]}


def test_custom_create_template_and_source_template_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        CreateCardRequest(
            card_kind="enterprise",
            display_name="企业名片",
            title="企业主页",
            template_source_card_id=uuid.uuid4(),
            template_document=_faq_document(mode="all_published"),
        )


async def test_custom_create_template_uses_the_same_resource_validation() -> None:
    scope = _catalog_scope()
    document = _faq_document(mode="all_published")
    body = CreateCardRequest(
        card_kind="enterprise",
        display_name="企业名片",
        title="企业主页",
        template_document=document,
    )
    store = CatalogStore(cast(Any, object()))
    store._validate_enterprise_template_resources = AsyncMock(return_value=document)  # type: ignore[method-assign]
    store._resolve_card_composer_template = AsyncMock()  # type: ignore[method-assign]

    resolved = await store._resolve_create_template(
        cast(Any, object()),
        scope=scope,
        body=body,
    )

    assert resolved is document
    store._validate_enterprise_template_resources.assert_awaited_once()  # type: ignore[attr-defined]
    store._resolve_card_composer_template.assert_not_awaited()  # type: ignore[attr-defined]


async def test_source_card_template_is_revalidated_before_copy() -> None:
    scope = _catalog_scope()
    source_id = uuid.uuid4()
    document = _faq_document(mode="all_published")
    source = SimpleNamespace(
        card_kind=SimpleNamespace(value="enterprise"),
        settings={"enterprise_template_draft": document.model_dump(mode="json")},
    )
    store = CatalogStore(cast(Any, object()))
    store._card = AsyncMock(return_value=source)  # type: ignore[method-assign]
    store._validate_enterprise_template_resources = AsyncMock(return_value=document)  # type: ignore[method-assign]

    resolved = await store._resolve_card_composer_template(
        cast(Any, object()),
        scope=scope,
        card_kind="enterprise",
        source_card_id=source_id,
    )

    store._validate_enterprise_template_resources.assert_awaited_once()  # type: ignore[attr-defined]
    validation_call = store._validate_enterprise_template_resources.await_args  # type: ignore[attr-defined]
    assert validation_call.kwargs["scope"] == scope
    assert validation_call.kwargs["document"] is resolved
    assert validation_call.kwargs["require_public_cases"] is False


def test_selected_faq_query_pins_every_public_and_scope_boundary() -> None:
    scope = _catalog_scope()
    sql = _compiled(eligible_faq_document_statement(scope, {uuid.uuid4()}))

    assert str(scope.tenant_id) in sql
    assert str(scope.company_id) in sql
    assert "knowledge_documents.source_type = 'faq'" in sql
    assert "knowledge_documents.status = 'published'" in sql
    assert "knowledge_documents.current_version_id IS NOT NULL" in sql
    assert "knowledge_chunks.version_id = knowledge_documents.current_version_id" in sql
    assert "knowledge_chunks.is_active IS true" in sql
    assert "knowledge_chunks.visibility = 'public'" in sql
    assert "knowledge_chunks.tenant_id" in sql
    assert "knowledge_chunks.company_id" in sql


async def test_selected_faq_validation_accepts_only_the_complete_eligible_set() -> None:
    faq_id = uuid.uuid4()
    scope = _catalog_scope()
    session = AsyncMock()
    session.scalars.return_value = _Rows([faq_id])
    store = CatalogStore(cast(Any, object()))

    result = await store._validate_enterprise_template_resources(
        session,
        scope=scope,
        document=_faq_document(ids=[faq_id]),
        require_public_cases=False,
    )

    assert result.blocks[1].faq_document_ids == [faq_id]


@pytest.mark.parametrize(
    "ineligible_reason", ["other_company", "unpublished", "internal", "inactive"]
)
async def test_selected_faq_validation_rejects_every_ineligible_state(
    ineligible_reason: str,
) -> None:
    del ineligible_reason
    faq_id = uuid.uuid4()
    session = AsyncMock()
    session.scalars.return_value = _Rows([])
    store = CatalogStore(cast(Any, object()))

    with pytest.raises(ApiError) as captured:
        await store._validate_enterprise_template_resources(
            session,
            scope=_catalog_scope(),
            document=_faq_document(ids=[faq_id]),
            require_public_cases=False,
        )

    assert captured.value.code == "TEMPLATE_FAQ_OUT_OF_SCOPE"


async def test_public_faq_projection_preserves_selected_order_and_legacy_id() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    session = AsyncMock()
    session.execute.return_value = _Rows(
        [
            SimpleNamespace(
                document_id=first_id,
                source_id="faq:first",
                title="第一个问题",
                text="第一段",
                ordinal=0,
                metadata_json={"source_label": "FAQ"},
            ),
            SimpleNamespace(
                document_id=first_id,
                source_id="faq:first",
                title="第一个问题",
                text="第二段",
                ordinal=1,
                metadata_json={},
            ),
            SimpleNamespace(
                document_id=second_id,
                source_id="faq:second",
                title="第二个问题",
                text="第二个答案",
                ordinal=0,
                metadata_json={},
            ),
        ]
    )
    template = {
        "blocks": [
            {
                "type": "faq",
                "faq_mode": "selected",
                "faq_document_ids": [str(second_id), str(first_id)],
            }
        ]
    }

    items = await _public_faq_items(
        session,
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        enterprise_template=template,
    )

    assert [item.document_id for item in items] == [second_id, first_id]
    assert [item.id for item in items] == ["faq:second", "faq:first"]
    assert items[1].answer == "第一段\n\n第二段"
    sql = _compiled(session.execute.await_args.args[0])
    assert "knowledge_documents.source_type = 'faq'" in sql
    assert "knowledge_documents.status = 'published'" in sql
    assert "knowledge_chunks.is_active IS true" in sql
    assert "knowledge_chunks.visibility = 'public'" in sql


def test_admin_selectable_faq_filter_is_public_safe_and_company_scoped() -> None:
    scope = _admin_scope()
    sql = _compiled(select(KnowledgeDocument.id).where(*selectable_faq_filters(scope)))

    assert str(scope.tenant_id) in sql
    assert str(scope.company_id) in sql
    assert "knowledge_documents.source_type = 'faq'" in sql
    assert "knowledge_documents.status = 'published'" in sql
    assert "knowledge_documents.current_version_id IS NOT NULL" in sql
    assert "knowledge_chunks.version_id = knowledge_documents.current_version_id" in sql
    assert "knowledge_chunks.is_active IS true" in sql
    assert "knowledge_chunks.visibility = 'public'" in sql


async def test_admin_selectable_answer_is_built_from_public_chunks_only() -> None:
    document_id = uuid.uuid4()
    session = AsyncMock()
    session.execute.return_value = _Rows(
        [
            SimpleNamespace(document_id=document_id, text="公开答案第一段"),
            SimpleNamespace(document_id=document_id, text="公开答案第二段"),
        ]
    )
    store = AdminStore(cast(Any, object()), cast(Any, object()))

    answers = await store._selectable_faq_answers(
        session,
        scope=_admin_scope(),
        documents=[SimpleNamespace(id=document_id)],
    )

    assert answers == {document_id: "公开答案第一段\n\n公开答案第二段"}
    sql = _compiled(session.execute.await_args.args[0])
    assert "knowledge_chunks.visibility = 'public'" in sql
    assert "knowledge_chunks.is_active IS true" in sql
