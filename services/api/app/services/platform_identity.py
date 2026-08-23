from __future__ import annotations

import secrets
import uuid


def normalize_social_credit_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def business_tenant_key(
    *,
    subject_type: str,
    social_credit_code: str | None,
    company_id: uuid.UUID,
) -> str:
    normalized_code = normalize_social_credit_code(social_credit_code)
    if subject_type == "domestic_enterprise" and normalized_code:
        return normalized_code
    return f"org-{company_id.hex[:24]}"


def tenant_slug_from_business_key(value: str) -> str:
    slug = "".join(
        character
        for character in value.casefold()
        if character.isalnum() or character == "-"
    )
    slug = slug.strip("-")
    if len(slug) < 3:
        slug = f"org-{slug or 'tenant'}"
    return slug[:64].rstrip("-")


def generate_temporary_password() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "Tmp-" + "".join(secrets.choice(alphabet) for _ in range(16)) + "!"


__all__ = [
    "business_tenant_key",
    "generate_temporary_password",
    "normalize_social_credit_code",
    "tenant_slug_from_business_key",
]
