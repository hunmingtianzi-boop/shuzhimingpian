from __future__ import annotations

import pytest

from app.api.errors import ApiError
from app.core.config import Settings
from app.services.wecom_js_sdk import (
    build_wecom_js_sdk_signatures,
    normalize_public_card_js_sdk_url,
)


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "public_card_base_url": "https://card.cfeifan.com",
        "staff_auth_cookie_secure": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_normalize_public_card_js_sdk_url_keeps_query_and_drops_fragment() -> None:
    value = normalize_public_card_js_sdk_url(
        value="https://card.cfeifan.com/c/xusongbo?from=wecom#profile",
        slug="xusongbo",
        settings=_settings(),
    )

    assert value == "https://card.cfeifan.com/c/xusongbo?from=wecom"


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example/c/xusongbo",
        "http://card.cfeifan.com/c/xusongbo",
        "https://card.cfeifan.com/c/another-card",
    ],
)
def test_normalize_public_card_js_sdk_url_rejects_other_targets(value: str) -> None:
    with pytest.raises(ApiError) as error:
        normalize_public_card_js_sdk_url(
            value=value,
            slug="xusongbo",
            settings=_settings(),
        )

    assert error.value.code == "WECOM_JS_SDK_URL_INVALID"


def test_build_wecom_js_sdk_signatures_matches_wecom_sha1_contract() -> None:
    signatures = build_wecom_js_sdk_signatures(
        url="https://card.cfeifan.com/c/xusongbo",
        config_ticket="corp-ticket",
        agent_config_ticket="agent-ticket",
        timestamp=1_700_000_000,
        nonce_str="nonce",
    )

    assert signatures.config_signature == "3a1a2ce0b3b5ed1c76daec99a2882418f6f6b881"
    assert signatures.agent_config_signature == "ab111bd605a9e04223783db1325a6f9ab032b3b6"
    assert signatures.config_signature != signatures.agent_config_signature
