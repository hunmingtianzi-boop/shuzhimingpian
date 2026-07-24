from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.cli.bootstrap_platform_admin import (
    PlatformBootstrapInput,
    bootstrap_platform_admin,
)
from app.cli.seed_content import (
    deterministic_id,
    load_content_package,
    seed_package,
)
from app.core.config import Settings
from app.db.models import AuditLog, ModelConfig, PromptVersion
from app.services.auth_store import AuthStore

ROOT = Path(__file__).resolve().parents[3]

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_PLATFORM_INTEGRATION") != "1",
        reason="set RUN_PLATFORM_INTEGRATION=1 against a disposable migrated database",
    ),
]


@pytest.mark.asyncio
async def test_seed_reuses_equivalent_ai_configuration_with_other_ids() -> None:
    settings = Settings()
    slug = f"seed-idempotency-{uuid.uuid4().hex[:12]}"
    package = load_content_package(
        ROOT / "packages" / "tenant-content" / "template.knowledge.json"
    )
    package = package.model_copy(
        update={
            "tenant": package.tenant.model_copy(
                update={"slug": slug, "name": "Seed Idempotency Tenant"}
            ),
            "company": package.company.model_copy(
                update={"slug": slug, "name": "Seed Idempotency Company"}
            ),
            "card": package.card.model_copy(update={"slug": slug}),
        }
    )
    tenant_id = deterministic_id(slug, "tenant")
    company_id = deterministic_id(slug, "company")
    replacement_prompt_id = uuid.uuid4()
    replacement_model_id = uuid.uuid4()
    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    sessions = async_sessionmaker(runtime, expire_on_commit=False)
    try:
        async with sessions() as session, session.begin():
            await seed_package(session, package, settings)

        async with owner.begin() as connection:
            await connection.execute(
                update(PromptVersion)
                .where(
                    PromptVersion.tenant_id == tenant_id,
                    PromptVersion.company_id == company_id,
                )
                .values(id=replacement_prompt_id)
            )
            await connection.execute(
                update(ModelConfig)
                .where(
                    ModelConfig.tenant_id == tenant_id,
                    ModelConfig.company_id == company_id,
                )
                .values(id=replacement_model_id)
            )

        async with sessions() as session, session.begin():
            await seed_package(session, package, settings)

        async with owner.connect() as connection:
            prompt_ids = (
                await connection.execute(
                    select(PromptVersion.id).where(
                        PromptVersion.tenant_id == tenant_id,
                        PromptVersion.company_id == company_id,
                    )
                )
            ).scalars().all()
            model_ids = (
                await connection.execute(
                    select(ModelConfig.id).where(
                        ModelConfig.tenant_id == tenant_id,
                        ModelConfig.company_id == company_id,
                    )
                )
            ).scalars().all()
        assert prompt_ids == [replacement_prompt_id]
        assert model_ids == [replacement_model_id]
    finally:
        await runtime.dispose()
        await owner.dispose()


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_audited_and_login_ready() -> None:
    settings = Settings()
    suffix = uuid.uuid4().hex[:12]
    account = f"platform-{suffix}@example.test"
    password = "Integration-Platform-Password-2026!"  # noqa: S105
    bootstrap = PlatformBootstrapInput(
        _env_file=None,
        tenant_slug="template",
        account=account,
        password=password,
        display_name="Platform Integration Admin",
        confirm="CREATE_FIRST_PLATFORM_ADMIN",
    )

    first = await bootstrap_platform_admin(settings, bootstrap)
    second = await bootstrap_platform_admin(settings, bootstrap)

    assert first.created is True
    assert second.created is False
    assert second.tenant_id == first.tenant_id
    assert second.company_id == first.company_id
    assert second.user_id == first.user_id
    assert second.membership_id == first.membership_id

    runtime = create_async_engine(settings.database_url, pool_pre_ping=True)
    owner = create_async_engine(settings.migration_database_url or settings.database_url)
    try:
        authentication = await AuthStore(
            async_sessionmaker(runtime, expire_on_commit=False),
            settings,
        ).login(account=account, credential=password)
        assert authentication.identity.role == "platform_admin"
        assert authentication.identity.permissions == ("*",)

        async with owner.connect() as connection:
            action = await connection.scalar(
                select(AuditLog.action).where(
                    AuditLog.resource_id == uuid.UUID(first.membership_id)
                )
            )
        assert action == "platform.admin.bootstrap"
    finally:
        await runtime.dispose()
        await owner.dispose()
