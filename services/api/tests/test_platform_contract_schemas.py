from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.platform_schemas import (
    PLATFORM_FORBIDDEN_RESPONSE_FIELDS,
    CreatePlatformLlmProfileRequest,
    PlatformCardProjection,
    PlatformEnterpriseDetail,
    PlatformLlmProfileRecord,
    PlatformOnboardingSessionRecord,
    StartPlatformOnboardingRequest,
)


def test_platform_enterprise_detail_is_an_explicit_private_field_free_projection() -> None:
    now = datetime.now(UTC)
    detail = PlatformEnterpriseDetail.model_validate(
        {
            "tenant_id": uuid4(),
            "tenant_slug": "acme",
            "tenant_name": "Acme Tenant",
            "company_id": uuid4(),
            "company_name": "Acme",
            "status": "active",
            "version": 2,
            "onboarding_status": "content_pending",
            "profile_completion": 60,
            "employee_count": 3,
            "card_count": 2,
            "published_card_count": 1,
            "visits_30d": 12,
            "conversations_30d": 4,
            "leads_30d": 1,
            "cards": [
                {
                    "id": uuid4(),
                    "card_kind": "enterprise",
                    "display_name": "Alice",
                    "title": "Founder",
                    "status": "published",
                    "updated_at": now,
                    "share_url": "https://cards.example.test/c/card-1",
                }
            ],
            "created_at": now,
            "updated_at": now,
        }
    )

    payload = detail.model_dump(mode="json")
    assert set(payload).isdisjoint(PLATFORM_FORBIDDEN_RESPONSE_FIELDS)
    assert set(payload["cards"][0]).isdisjoint(PLATFORM_FORBIDDEN_RESPONSE_FIELDS)

    with pytest.raises(ValidationError):
        PlatformEnterpriseDetail.model_validate({**payload, "visitor_email": "private@test"})


def test_non_public_cards_cannot_receive_a_share_url() -> None:
    with pytest.raises(ValidationError):
        PlatformCardProjection.model_validate(
            {
                "id": uuid4(),
                "card_kind": "employee",
                "display_name": "Draft owner",
                "title": "Draft",
                "status": "draft",
                "updated_at": datetime.now(UTC),
                "share_url": "https://cards.example.test/c/draft-card",
            }
        )


def test_llm_read_model_never_accepts_a_plain_or_encrypted_key() -> None:
    profile = PlatformLlmProfileRecord.model_validate(
        {
            "id": uuid4(),
            "name": "Primary",
            "purpose": "chat_main",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "key_configured": True,
            "key_hint": "...abcd",
            "enabled": True,
            "is_active": True,
            "version": 1,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )

    payload = profile.model_dump(mode="json")
    assert "api_key" not in payload
    assert "api_key_ciphertext" not in payload
    assert payload["allow_general_answers"] is False
    assert payload["faq_fast_path_enabled"] is False

    for forbidden in ("api_key", "api_key_ciphertext"):
        with pytest.raises(ValidationError):
            PlatformLlmProfileRecord.model_validate({**payload, forbidden: "secret"})

    request = CreatePlatformLlmProfileRequest.model_validate(
        {
            "name": "Primary",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "api_key": "write-only-secret",
        }
    )
    assert request.api_key is not None
    assert request.api_key.get_secret_value() == "write-only-secret"
    assert request.allow_general_answers is False
    assert request.faq_fast_path_enabled is False


@pytest.mark.parametrize("field", ["tenant_id", "company_id", "target_tenant_id"])
def test_onboarding_requests_cannot_select_a_target_scope(field: str) -> None:
    with pytest.raises(ValidationError):
        StartPlatformOnboardingRequest.model_validate(
            {
                "tenant_slug": "acme",
                "admin_account": "admin@acme.test",
                "admin_display_name": "Acme Admin",
                field: str(uuid4()),
            }
        )


def test_onboarding_session_read_model_hides_provisional_scope_ids() -> None:
    session = PlatformOnboardingSessionRecord.model_validate(
        {
            "id": uuid4(),
            "status": "draft",
            "tenant_slug": "acme",
            "admin_account": "admin@acme.test",
            "admin_display_name": "Acme Admin",
            "initial_card_display_name": "Acme",
            "initial_card_title": "Acme Official Card",
            "version": 1,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )

    payload = session.model_dump(mode="json")
    assert "tenant_id" not in payload
    assert "company_id" not in payload
    assert "admin_password" not in payload
    assert payload["admin_account"] == "admin@acme.test"
    assert payload["admin_display_name"] == "Acme Admin"
    assert payload["initial_card_display_name"] == "Acme"
    assert payload["initial_card_title"] == "Acme Official Card"
    assert set(payload).isdisjoint(PLATFORM_FORBIDDEN_RESPONSE_FIELDS)

    with pytest.raises(ValidationError):
        PlatformOnboardingSessionRecord.model_validate(
            {**payload, "admin_password": "must-never-be-returned"}
        )


def test_terminal_onboarding_session_allows_review_projection_to_be_redacted() -> None:
    session = PlatformOnboardingSessionRecord.model_validate(
        {
            "id": uuid4(),
            "status": "cancelled",
            "tenant_slug": "acme",
            "version": 2,
            "admin_account": None,
            "admin_display_name": None,
            "initial_card_display_name": None,
            "initial_card_title": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
    )

    payload = session.model_dump(mode="json")
    assert payload["admin_account"] is None
    assert payload["admin_display_name"] is None
    assert payload["initial_card_display_name"] is None
    assert payload["initial_card_title"] is None
