from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.api.catalog_schemas import CreateCardRequest
from app.api.errors import ApiError
from app.db.models import Card, CardKind, ContentStatus, LifecycleStatus, Membership
from app.services.catalog_store import (
    CatalogScope,
    CatalogStore,
    EmployeeIdentityProjection,
    _employee_card_expression_settings,
    _without_employee_identity,
)
from app.services.public_store import _employee_contact_fields, _public_employee_identity


class _MappingResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> _MappingResult:
        return self

    def one_or_none(self) -> dict[str, Any] | None:
        return self._row


class _ExecuteSession:
    def __init__(self, row: dict[str, Any] | None, *, scalar_value: object | None = None) -> None:
        self.row = row
        self.scalar_value = scalar_value
        self.statements: list[object] = []

    async def execute(self, statement: object) -> _MappingResult:
        self.statements.append(statement)
        return _MappingResult(self.row)

    async def scalar(self, statement: object) -> object | None:
        self.statements.append(statement)
        return self.scalar_value


def _scope() -> CatalogScope:
    return CatalogScope(
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        role="company_admin",
    )


def _employee_card(*, owner_user_id: uuid.UUID | None = None) -> Card:
    owner_id = owner_user_id or uuid.uuid4()
    now = datetime.now(UTC)
    return Card(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        card_kind=CardKind.EMPLOYEE,
        owner_user_id=owner_id,
        responsible_user_id=owner_id,
        slug="c-" + "a" * 36,
        display_name="legacy duplicate name",
        status=ContentStatus.DRAFT,
        settings={
            "title": "legacy duplicate title",
            "avatar_url": "https://legacy.example/avatar.png",
            "business_summary": "legacy duplicate summary",
            "assistant_name": "员工助手",
        },
        version=3,
        created_at=now,
        updated_at=now,
    )


def test_membership_owns_company_scoped_employee_profile_columns() -> None:
    assert Membership.__table__.c.job_title.type.length == 200
    assert Membership.__table__.c.avatar_url.type.length == 2_048
    assert Membership.__table__.c.business_summary.nullable is True


def test_employee_card_write_persists_expression_without_identity_copy() -> None:
    body = CreateCardRequest(
        owner_user_id=uuid.uuid4(),
        display_name="client supplied duplicate name",
        title="client supplied duplicate title",
        avatar_url="https://cdn.example/avatar.png",
        assistant_name="业务助手",
        welcome_message="欢迎咨询",
        suggested_questions=["可以提供什么服务？"],
    )

    stored = _employee_card_expression_settings(body)

    assert stored == {
        "assistant_name": "业务助手",
        "welcome_message": "欢迎咨询",
        "suggested_questions": ["可以提供什么服务？"],
        "policy_versions": {},
        "employee_contact_visibility": [],
    }
    assert not {"display_name", "title", "avatar_url", "business_summary"} & stored.keys()


def test_existing_card_identity_copies_are_removed_without_losing_expression() -> None:
    cleaned = _without_employee_identity(_employee_card().settings)

    assert cleaned == {"assistant_name": "员工助手"}


def test_managed_employee_record_uses_live_identity_projection() -> None:
    card = _employee_card()
    store = CatalogStore(
        cast(Any, object()),
        public_card_base_url="http://127.0.0.1:4173",
        allow_insecure_http=True,
    )
    identity = EmployeeIdentityProjection(
        display_name="当前员工姓名",
        job_title="解决方案总监",
        avatar_url="https://cdn.example/current.png",
        business_summary="当前成员资料",
    )

    record = store._managed_card_record(card, employee_identity=identity)

    assert record.display_name == "当前员工姓名"
    assert record.title == "解决方案总监"
    assert record.avatar_url == "https://cdn.example/current.png"


@pytest.mark.asyncio
async def test_catalog_identity_rejects_inactive_member_for_mutating_flow() -> None:
    scope = _scope()
    session = _ExecuteSession(
        {
            "display_name": "停用员工",
            "user_status": LifecycleStatus.ACTIVE,
            "user_deleted_at": None,
            "job_title": "顾问",
            "avatar_url": None,
            "business_summary": None,
            "membership_status": LifecycleStatus.DISABLED,
        }
    )
    store = CatalogStore(
        cast(Any, object()),
        public_card_base_url="http://127.0.0.1:4173",
        allow_insecure_http=True,
    )

    with pytest.raises(ApiError) as captured:
        await store._employee_identity(
            cast(Any, session),
            scope,
            uuid.uuid4(),
            require_active=True,
        )

    assert captured.value.status_code == 422
    assert captured.value.code == "INVALID_CARD_OWNER"


@pytest.mark.asyncio
async def test_catalog_rejects_a_second_employee_card_for_the_same_employee() -> None:
    scope = _scope()
    store = CatalogStore(
        cast(Any, object()),
        public_card_base_url="http://127.0.0.1:4173",
        allow_insecure_http=True,
    )

    with pytest.raises(ApiError) as captured:
        await store._ensure_employee_card_available(
            cast(Any, _ExecuteSession(None, scalar_value=uuid.uuid4())),
            scope=scope,
            owner_user_id=uuid.uuid4(),
        )

    assert captured.value.status_code == 409
    assert captured.value.code == "EMPLOYEE_CARD_EXISTS"


@pytest.mark.asyncio
async def test_catalog_identity_reflects_membership_title_without_card_edit() -> None:
    scope = _scope()
    session = _ExecuteSession(
        {
            "display_name": "真实姓名",
            "user_status": LifecycleStatus.ACTIVE,
            "user_deleted_at": None,
            "job_title": "新职位",
            "avatar_url": "https://cdn.example/new-avatar.png",
            "business_summary": "新业务摘要",
            "membership_status": LifecycleStatus.ACTIVE,
        }
    )
    store = CatalogStore(
        cast(Any, object()),
        public_card_base_url="http://127.0.0.1:4173",
        allow_insecure_http=True,
    )

    identity = await store._employee_identity(
        cast(Any, session),
        scope,
        uuid.uuid4(),
        require_active=True,
    )

    assert identity == EmployeeIdentityProjection(
        display_name="真实姓名",
        job_title="新职位",
        avatar_url="https://cdn.example/new-avatar.png",
        business_summary="新业务摘要",
    )
    statement = str(session.statements[0])
    assert "memberships.tenant_id" in statement
    assert "memberships.company_id" in statement


@pytest.mark.asyncio
async def test_public_employee_identity_uses_user_and_membership_projection() -> None:
    card = _employee_card()
    session = _ExecuteSession(
        {
            "display_name": "公开姓名",
            "job_title": "客户成功负责人",
            "avatar_url": "https://cdn.example/public-avatar.png",
            "business_summary": "帮助企业把复杂方案转成可落地路径。",
            "email_ciphertext": b"email",
            "mobile_ciphertext": b"mobile",
        }
    )

    identity = await _public_employee_identity(
        cast(Any, session),
        card=card,
        cipher=cast(Any, SimpleNamespace(decrypt=lambda value: value.decode())),
    )

    assert identity.display_name == "公开姓名"
    assert identity.job_title == "客户成功负责人"
    assert identity.avatar_url == "https://cdn.example/public-avatar.png"
    assert identity.business_summary == "帮助企业把复杂方案转成可落地路径。"
    assert _employee_contact_fields(identity, {"mobile", "email"}) == [
        {"label": "工作手机", "value": "mobile", "href": "tel:mobile"},
        {"label": "工作邮箱", "value": "email", "href": "mailto:email"},
    ]
    assert _employee_contact_fields(identity, {"mobile"}) == [
        {"label": "工作手机", "value": "mobile", "href": "tel:mobile"},
    ]
    statement = str(session.statements[0])
    assert "users.status" in statement
    assert "memberships.status" in statement
    assert "memberships.company_id" in statement


@pytest.mark.asyncio
async def test_public_employee_identity_hides_inactive_or_out_of_scope_owner() -> None:
    with pytest.raises(ApiError) as captured:
        await _public_employee_identity(
            cast(Any, _ExecuteSession(None)),
            card=_employee_card(),
            cipher=cast(Any, SimpleNamespace(decrypt=lambda value: value.decode())),
        )

    assert captured.value.status_code == 404
    assert captured.value.code == "RESOURCE_NOT_FOUND"
