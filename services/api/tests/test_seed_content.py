from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cli.seed_content import (
    _should_bootstrap_staff,
    deterministic_id,
    load_content_package,
    should_activate_seed_version,
)
from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "filename,expected_documents",
    [("template.knowledge.json", 5), ("tuotu.knowledge.json", 12)],
)
def test_content_packages_validate(filename: str, expected_documents: int) -> None:
    package = load_content_package(ROOT / "packages" / "tenant-content" / filename)

    assert package.card.slug == package.company.slug
    assert len(package.documents) == expected_documents
    assert all(document.content for document in package.documents)
    assert package.forbidden_topics


def test_tuotu_package_bootstraps_the_public_business_catalog() -> None:
    package = load_content_package(
        ROOT / "packages" / "tenant-content" / "tuotu.knowledge.json"
    )

    assert len(package.products) == 4
    assert len(package.case_studies) == 3
    assert [field.field_type for field in package.contact_fields] == ["website"]
    assert {rule.action for rule in package.forbidden_topics} == {
        "refuse",
        "handoff",
        "safe_template",
    }


def test_tuotu_common_intents_have_exact_faq_aliases() -> None:
    package = load_content_package(
        ROOT / "packages" / "tenant-content" / "tuotu.knowledge.json"
    )
    documents = {document.external_id: document for document in package.documents}

    assert package.knowledge_sequence == 9
    cooperation_aliases = documents["faq-cooperation"].metadata["aliases"]
    assert "合作" in cooperation_aliases
    assert "我想合作" in cooperation_aliases
    assert "我希望合作" in cooperation_aliases
    business_aliases = documents["faq-businesses"].metadata["aliases"]
    assert "三大业务" in business_aliases
    assert "核心业务" in business_aliases
    assert "我想加入" in documents["faq-beginner"].metadata["aliases"]
    assert "怎么联系？" in documents["faq-contact"].metadata["aliases"]


def test_content_package_rejects_utf8_text_decoded_as_latin1(tmp_path: Path) -> None:
    source_path = ROOT / "packages" / "tenant-content" / "tuotu.knowledge.json"
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    payload["documents"][0]["content"] = payload["documents"][0]["content"].encode(
        "utf-8"
    ).decode("latin-1")
    corrupted_path = tmp_path / "corrupted.knowledge.json"
    corrupted_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValidationError, match="forbidden control character"):
        load_content_package(corrupted_path)


def test_seed_identifiers_are_stable_and_tenant_specific() -> None:
    assert deterministic_id("tuotu", "company") == deterministic_id("tuotu", "company")
    assert deterministic_id("tuotu", "company") != deterministic_id("template", "company")


def test_admin_bootstrap_is_limited_to_the_explicit_tenant_slug() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        admin_bootstrap_tenant_slug="tuotu",
        admin_bootstrap_account="admin@example.test",
        admin_bootstrap_password="a-strong-bootstrap-password",  # noqa: S106
    )

    assert _should_bootstrap_staff(settings, "tuotu")
    assert not _should_bootstrap_staff(settings, "template")


def test_startup_seed_never_replaces_an_admin_published_version() -> None:
    seed_version_id = uuid.uuid4()

    assert should_activate_seed_version(None, seed_version_id)
    assert should_activate_seed_version(seed_version_id, seed_version_id)
    assert not should_activate_seed_version(uuid.uuid4(), seed_version_id)


def test_startup_seed_promotes_a_newer_seed_owned_version() -> None:
    assert should_activate_seed_version(
        uuid.uuid4(),
        uuid.uuid4(),
        current_is_seed=True,
    )
