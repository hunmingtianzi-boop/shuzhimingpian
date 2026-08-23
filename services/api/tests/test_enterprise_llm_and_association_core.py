from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.api.admin_schemas import EnterpriseLlmAccess, UpdateEnterpriseLlmAccessRequest
from app.api.errors import ApiError
from app.api.platform_schemas import CreatePlatformLlmProfileRequest
from app.core.config import Settings
from app.core.pii import PiiCipher
from app.db.models import (
    AssociationCompanyMembership,
    Company,
    CompanyLLMConfiguration,
    PlatformLLMProfile,
)
from app.services import platform_llm_profiles as llm_module
from app.services.enterprise_llm_access import EnterpriseLLMAccessService, EnterpriseLLMActor
from app.services.platform_associations import PlatformAssociationActor, PlatformAssociationService


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        field_encryption_key="test-field-encryption-material-32-bytes",
        field_encryption_key_ref="test/enterprise-llm/v1",
    )


def _profile(settings: Settings) -> PlatformLLMProfile:
    cipher = PiiCipher.from_settings(settings)
    return PlatformLLMProfile(
        id=uuid.uuid4(),
        name="平台批准模型",
        purpose="chat_main",
        provider="openai_compatible",
        base_url="https://provider.example.test/v1",
        api_key_ciphertext=cipher.encrypt("platform-placeholder-key"),
        api_key_key_ref=cipher.key_ref,
        api_key_hint="••••-key",
        model="approved-model",
        thinking="disabled",
        reasoning_effort=None,
        timeout_seconds=Decimal("10"),
        max_retries=0,
        max_concurrency=10,
        max_output_tokens=1000,
        temperature=Decimal("0.1"),
        daily_budget_cny=Decimal("100"),
        input_price_cny_per_million=Decimal("1"),
        output_price_cny_per_million=Decimal("2"),
        allow_general_answers=False,
        faq_fast_path_enabled=True,
        enabled=True,
        is_active=True,
        version=2,
        last_test_status="untested",
        updated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_args: object) -> None:
        return None


class _Session:
    def __init__(self, values: list[object | None]) -> None:
        self.values = values

    async def __aenter__(self) -> _Session:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction()

    async def execute(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def scalar(self, _statement: object) -> object | None:
        return self.values.pop(0) if self.values else None


class _Factory:
    def __init__(self, values: list[object | None]) -> None:
        self.session = _Session(values)

    def __call__(self) -> _Session:
        return self.session


def test_enterprise_llm_model_and_migration_keep_secrets_encrypted_and_scoped() -> None:
    columns = CompanyLLMConfiguration.__table__.columns
    constraints = {constraint.name for constraint in CompanyLLMConfiguration.__table__.constraints}
    migration = (
        (
            Path(__file__).parents[1]
            / "migrations/versions/20260823_0049_enterprise_llm_and_association_boundaries.py"
        )
        .read_text(encoding="utf-8")
        .casefold()
    )

    assert "api_key" not in columns
    assert {"api_key_ciphertext", "api_key_key_ref", "api_key_hint"} <= set(columns.keys())
    assert any(name and name.endswith("credential_state") for name in constraints)
    assert "enable row level security" in migration
    assert "app.scope_matches(tenant_id, company_id)" in migration
    assert "app.platform_actor_allowed()" in migration
    assert "api_key varchar" not in migration
    assert "refusing to drop company_llm_configurations" in migration


def test_platform_profile_default_fits_the_persistence_token_constraint() -> None:
    request_default = CreatePlatformLlmProfileRequest.model_fields[
        "max_output_tokens"
    ].default
    model_constraints = {
        str(constraint.sqltext)
        for constraint in PlatformLLMProfile.__table__.constraints
        if hasattr(constraint, "sqltext")
    }
    migration = (
        Path(__file__).parents[1]
        / "migrations/versions/20260823_0049_enterprise_llm_and_association_boundaries.py"
    ).read_text(encoding="utf-8")

    assert request_default == 32768
    assert any("max_output_tokens <= 65536" in sql for sql in model_constraints)
    assert "max_output_tokens >= 128 AND max_output_tokens <= 65536" in migration


def test_association_model_is_cross_company_reference_not_parent_tenancy() -> None:
    columns = AssociationCompanyMembership.__table__.columns
    constraints = {
        constraint.name for constraint in AssociationCompanyMembership.__table__.constraints
    }

    assert {
        "association_tenant_id",
        "association_company_id",
        "member_tenant_id",
        "member_company_id",
        "member_tier",
        "allocated_seats",
        "benefits",
    } <= set(columns.keys())
    assert "parent_tenant_id" not in columns
    assert "uq_association_company_memberships_pair" in constraints
    assert any(name and name.endswith("association_member_distinct") for name in constraints)


def test_enterprise_llm_response_and_request_never_serialize_plaintext_key() -> None:
    profile_id = uuid.uuid4()
    response = EnterpriseLlmAccess(
        platform_profile_id=profile_id,
        profile_name="平台批准模型",
        provider="openai_compatible",
        base_url="https://provider.example.test/v1",
        model="approved-model",
        mode="byok",
        daily_budget_cny=10,
        platform_budget_ceiling_cny=100,
        enabled=True,
        key_configured=True,
        key_hint="••••1234",
        version=1,
        configured=True,
        delegated=False,
        updated_at=datetime.now(UTC),
    )
    request = UpdateEnterpriseLlmAccessRequest(
        platform_profile_id=profile_id,
        mode="byok",
        daily_budget_cny=10,
        expected_version=0,
        api_key="enterprise-placeholder-key",
    )

    assert "api_key" not in response.model_dump()
    assert "enterprise-placeholder-key" not in repr(request)


def test_company_and_association_role_guards_are_fail_closed() -> None:
    company_actor = EnterpriseLLMActor(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="card_owner",
    )
    platform_actor = PlatformAssociationActor(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        role="company_admin",
    )

    with pytest.raises(ApiError) as company_denied:
        EnterpriseLLMAccessService._require_company_admin(company_actor)
    with pytest.raises(ApiError) as platform_denied:
        PlatformAssociationService._require_platform(platform_actor)
    assert company_denied.value.status_code == 403
    assert platform_denied.value.status_code == 403


async def test_company_byok_runtime_uses_approved_profile_and_company_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    profile = _profile(settings)
    cipher = PiiCipher.from_settings(settings)
    company_key = "enterprise-placeholder-key"
    company_config = CompanyLLMConfiguration(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        company_id=uuid.uuid4(),
        platform_profile_id=profile.id,
        mode="byok",
        api_key_ciphertext=cipher.encrypt(company_key),
        api_key_key_ref=cipher.key_ref,
        api_key_hint="••••-key",
        daily_budget_cny=Decimal("25"),
        enabled=True,
        version=4,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    async def no_scope(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(llm_module, "set_rls_context", no_scope)
    runtime = await llm_module.resolve_effective_chat_config(
        _Factory([company_config, profile]),  # type: ignore[arg-type]
        settings,
        tenant_id=company_config.tenant_id,
        company_id=company_config.company_id,
    )

    assert runtime.source == "company"
    assert runtime.model == "approved-model"
    assert runtime.daily_budget_cny == 25
    assert runtime.api_key.get_secret_value() == company_key
    assert company_key not in repr(runtime)


def test_association_projection_does_not_expose_member_private_data() -> None:
    company = Company(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="成员企业",
        normalized_name="成员企业",
        business_tenant_key="member-company",
        subject_type="domestic_enterprise",
    )
    membership = AssociationCompanyMembership(
        id=uuid.uuid4(),
        association_tenant_id=uuid.uuid4(),
        association_company_id=uuid.uuid4(),
        member_tenant_id=company.tenant_id,
        member_company_id=company.id,
        member_tier="理事单位",
        allocated_seats=3,
        benefits={"events": True},
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    view = PlatformAssociationService._view(membership, company)
    serialized: dict[str, Any] = (
        view.__dict__
        if hasattr(view, "__dict__")
        else {field: getattr(view, field) for field in view.__dataclass_fields__}
    )
    assert set(serialized) == {
        "id",
        "association_company_id",
        "company_id",
        "legal_name",
        "short_name",
        "business_tenant_key",
        "member_tier",
        "allocated_seats",
        "benefits",
        "version",
        "updated_at",
    }
    assert not {"email", "mobile", "content", "api_key"} & set(serialized)
