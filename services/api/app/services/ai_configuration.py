from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import DEFAULT_PROMPT_VERSION, PromptRegistry
from app.core.config import Settings
from app.db.models import ModelConfig, PromptStatus, PromptVersion

ENVIRONMENT_LLM_SECRET_REF = "environment-variable:LLM_API_KEY"  # noqa: S105


async def provision_chat_configuration(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    company_id: uuid.UUID,
    published_by: uuid.UUID,
    published_at: datetime,
    settings: Settings,
    secret_ref: str,
    change_summary: str,
) -> None:
    """Create or refresh the audit records required by the chat runtime."""

    prompt = PromptRegistry().get(DEFAULT_PROMPT_VERSION)
    prompt_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{company_id}:rag-prompt:{prompt.version}",
    )
    await session.execute(
        pg_insert(PromptVersion)
        .values(
            id=prompt_id,
            tenant_id=tenant_id,
            company_id=company_id,
            name=prompt.version,
            purpose="rag_answer",
            version_number=1,
            content=prompt.system_text,
            content_hash=hashlib.sha256(prompt.system_text.encode("utf-8")).hexdigest(),
            change_summary=change_summary,
            evaluation_result={"status": "requires_pilot_evaluation"},
            status=PromptStatus.PUBLISHED,
            published_by=published_by,
            published_at=published_at,
        )
        .on_conflict_do_nothing(constraint="uq_prompt_versions_name_version")
    )

    model_config_id = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"{company_id}:chat:{settings.llm_provider}",
    )
    parameters = {
        "thinking": settings.llm_thinking,
        "reasoning_effort": settings.llm_reasoning_effort,
        "temperature": settings.llm_temperature,
        "max_tokens": settings.llm_max_output_tokens,
    }
    await session.execute(
        pg_insert(ModelConfig)
        .values(
            id=model_config_id,
            tenant_id=tenant_id,
            company_id=company_id,
            purpose="chat",
            provider=settings.llm_provider,
            model_name=settings.llm_model,
            endpoint_region=None,
            secret_ref=secret_ref,
            timeout_ms=round(settings.llm_timeout_seconds * 1_000),
            max_retries=settings.llm_max_retries,
            max_concurrency=settings.llm_max_concurrency,
            daily_budget_cny=Decimal(str(settings.model_daily_budget_cny)),
            data_retention="no_training",
            enabled=True,
            parameters=parameters,
        )
        .on_conflict_do_update(
            constraint="uq_model_configs_purpose_provider",
            set_={
                "model_name": settings.llm_model,
                "secret_ref": secret_ref,
                "timeout_ms": round(settings.llm_timeout_seconds * 1_000),
                "max_retries": settings.llm_max_retries,
                "max_concurrency": settings.llm_max_concurrency,
                "daily_budget_cny": Decimal(str(settings.model_daily_budget_cny)),
                "enabled": True,
                "parameters": parameters,
            },
        )
    )
