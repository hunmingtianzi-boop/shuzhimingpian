from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.commercial_schemas import UpdateCommercialEntitlementRequest
from app.commercial.entitlements import (
    commercial_settings_payload,
    feature_is_enabled,
    resolve_commercial_entitlements,
)
from app.services.catalog_store import _effective_card_plugin_installations


def test_legacy_company_defaults_to_enterprise_without_disabling_existing_features() -> None:
    state = resolve_commercial_entitlements({})

    assert state.plan_code == "enterprise"
    assert all(state.features.values())
    assert all(value is None for value in state.limits.values())


def test_starter_plan_enables_only_starter_and_required_features() -> None:
    state = resolve_commercial_entitlements({"commercial_entitlements": {"plan_code": "starter"}})

    assert state.features["card.core"] is True
    assert state.features["customer.visits"] is True
    assert state.features["knowledge.manage"] is False
    assert state.features["data.exports"] is False


def test_company_overrides_can_open_or_close_overrideable_features() -> None:
    state = resolve_commercial_entitlements(
        {
            "commercial_entitlements": {
                "plan_code": "professional",
                "feature_overrides": {
                    "data.exports": True,
                    "customer.leads": False,
                    "card.core": False,
                    "unknown.feature": True,
                },
            }
        }
    )

    assert state.features["data.exports"] is True
    assert state.features["customer.leads"] is False
    assert state.features["card.core"] is True
    assert "unknown.feature" not in state.features


def test_commercial_settings_payload_normalizes_price_and_known_overrides() -> None:
    payload = commercial_settings_payload(
        plan_code="enterprise",
        billing_cycle="yearly",
        contract_price_cny=Decimal("12888.5"),
        feature_overrides={"integration.wecom": False, "unknown.feature": True},
        limit_overrides={"members.max": 25, "storage.mb": None, "unknown": 3},
    )

    assert payload == {
        "plan_code": "enterprise",
        "billing_cycle": "yearly",
        "contract_price_cny": "12888.50",
        "feature_overrides": {"integration.wecom": False},
        "limit_overrides": {"members.max": 25, "storage.mb": None},
    }
    assert feature_is_enabled({"commercial_entitlements": payload}, "integration.wecom") is False
    state = resolve_commercial_entitlements({"commercial_entitlements": payload})
    assert state.limit_overrides == {"members.max": 25, "storage.mb": None}
    assert state.limits["members.max"] == 25
    assert state.limits["storage.mb"] is None
    assert feature_is_enabled({}, "unknown.feature") is False


def test_card_plugin_installation_cannot_bypass_commercial_entitlement() -> None:
    installations = _effective_card_plugin_installations(
        {
            "commercial_entitlements": {"plan_code": "starter"},
            "card_plugin_installations": {
                "cf.card.faq": {
                    "plugin_version": "1.0.0",
                    "enabled": True,
                    "grants": ["knowledge.published.read"],
                }
            },
        }
    )

    assert installations["cf.system.identity"]["enabled"] is True
    assert installations["cf.card.actions"]["enabled"] is True
    assert installations["cf.card.faq"]["enabled"] is False


@pytest.mark.parametrize("invalid_value", [-1, 1.5, True, "10"])
def test_commercial_limit_overrides_reject_invalid_values(invalid_value: object) -> None:
    with pytest.raises(ValidationError):
        UpdateCommercialEntitlementRequest.model_validate(
            {
                "expected_version": 1,
                "plan_code": "professional",
                "limit_overrides": {"members.max": invalid_value},
            }
        )
