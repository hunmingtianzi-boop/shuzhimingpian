from __future__ import annotations

import os
import socket
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../../.env", "../../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    worker_database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://cf_ai_card_worker:change-me-worker-local-only@127.0.0.1:5432/"
        "cf_ai_card"
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    celery_broker_url: SecretStr = SecretStr("redis://localhost:6379/1")
    field_encryption_key: SecretStr = SecretStr("replace-with-kms-backed-key")
    field_encryption_key_ref: str = Field(default="local-v1", min_length=1, max_length=128)
    field_encryption_previous_keys: SecretStr | None = None
    worker_id: str = Field(default_factory=_default_worker_id, min_length=1, max_length=128)
    worker_log_level: str = "INFO"

    outbox_poll_seconds: float = Field(default=1.0, ge=0.2, le=60)
    outbox_batch_size: int = Field(default=20, ge=1, le=100)
    outbox_lease_seconds: int = Field(default=900, ge=30, le=3_600)
    outbox_heartbeat_seconds: int = Field(default=60, ge=5, le=600)
    outbox_max_attempts: int = Field(default=6, ge=1, le=50)
    outbox_backoff_base_seconds: int = Field(default=5, ge=1, le=3_600)
    outbox_backoff_max_seconds: int = Field(default=900, ge=1, le=86_400)
    export_retention_hours: int = Field(default=24, ge=1, le=168)
    export_max_rows: int = Field(default=100_000, ge=1, le=1_000_000)
    profile_retention_purge_seconds: int = Field(default=3_600, ge=60, le=86_400)
    visit_report_poll_seconds: float = Field(default=5.0, ge=5, le=600)
    visit_report_idle_seconds: int = Field(default=35, ge=10, le=86_400)
    visit_report_batch_size: int = Field(default=100, ge=1, le=500)
    platform_onboarding_retention_purge_seconds: int = Field(default=3_600, ge=60, le=86_400)
    scheduled_publish_poll_seconds: float = Field(default=5.0, ge=1, le=300)
    scheduled_publish_batch_size: int = Field(default=10, ge=1, le=100)
    scheduled_publish_lease_seconds: int = Field(default=900, ge=30, le=3_600)
    scheduled_publish_max_attempts: int = Field(default=6, ge=1, le=50)
    knowledge_import_poll_seconds: float = Field(default=3.0, ge=1, le=300)
    knowledge_import_batch_size: int = Field(default=10, ge=1, le=100)
    knowledge_import_lease_seconds: int = Field(default=900, ge=30, le=3_600)
    knowledge_import_max_attempts: int = Field(default=6, ge=1, le=50)
    knowledge_import_parse_timeout_seconds: int = Field(default=300, ge=30, le=900)
    content_import_poll_seconds: float = Field(default=2.0, ge=1, le=300)
    content_import_batch_size: int = Field(default=2, ge=1, le=20)
    content_import_lease_seconds: int = Field(default=900, ge=60, le=3_600)
    embedding_provider: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_dimension: int = Field(default=1_024, ge=64, le=4_096)
    embedding_timeout_seconds: float = Field(default=20.0, ge=2, le=120)

    wecom_corp_id: str | None = None
    wecom_agent_id: int | None = Field(default=None, ge=1)
    wecom_app_secret: SecretStr | None = None
    wecom_api_base_url: str = "https://qyapi.weixin.qq.com"
    wecom_proxy_url: str | None = None
    wecom_suite_id: str | None = None
    wecom_suite_secret: SecretStr | None = None
    wecom_timeout_seconds: float = Field(default=8.0, ge=1, le=30)
    admin_base_url: str | None = None

    worker_health_host: str = "0.0.0.0"  # noqa: S104 - container health endpoint
    worker_health_port: int = Field(default=8020, ge=1, le=65_535)
    worker_health_timeout_seconds: float = Field(default=3.0, ge=0.2, le=10)

    evaluation_dataset_dir: Path = Path("/eval-data")
    evaluation_suite_version: str = Field(default="v2", pattern=r"^v[0-9]+$")

    @field_validator("worker_id", "worker_log_level", "worker_health_host")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("worker setting cannot be blank")
        return normalized

    @field_validator(
        "wecom_corp_id",
        "wecom_agent_id",
        "wecom_app_secret",
        "wecom_proxy_url",
        "wecom_suite_id",
        "wecom_suite_secret",
        "admin_base_url",
        mode="before",
    )
    @classmethod
    def blank_wecom_values_are_unconfigured(cls, value: object) -> object | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_timing(self) -> "WorkerSettings":
        if self.outbox_heartbeat_seconds * 2 >= self.outbox_lease_seconds:
            raise ValueError("OUTBOX_HEARTBEAT_SECONDS must be less than half the lease")
        if self.outbox_backoff_base_seconds > self.outbox_backoff_max_seconds:
            raise ValueError("outbox backoff base cannot exceed maximum")
        configured = (
            bool(self.wecom_corp_id),
            self.wecom_agent_id is not None,
            self.wecom_app_secret is not None and bool(self.wecom_app_secret.get_secret_value()),
        )
        if any(configured) and not all(configured):
            raise ValueError(
                "WECOM_CORP_ID, WECOM_AGENT_ID and WECOM_APP_SECRET must be configured together"
            )
        suite_configured = (
            bool(self.wecom_suite_id),
            self.wecom_suite_secret is not None
            and bool(self.wecom_suite_secret.get_secret_value()),
        )
        if any(suite_configured) and not all(suite_configured):
            raise ValueError("WECOM_SUITE_ID and WECOM_SUITE_SECRET must be configured together")
        if self.app_env in {"staging", "production"}:
            url = self.worker_database_url.get_secret_value()
            if "change-me" in url or "cf_ai_card_worker" not in url:
                raise ValueError(
                    "WORKER_DATABASE_URL must use the managed least-privilege worker identity"
                )
            if "change-me" in self.celery_broker_url.get_secret_value():
                raise ValueError("CELERY_BROKER_URL must use managed credentials")
        return self

    @property
    def database_url(self) -> str:
        return self.worker_database_url.get_secret_value()

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url.get_secret_value()

    @property
    def redis_connection_url(self) -> str:
        return self.redis_url.get_secret_value()


@lru_cache(maxsize=1)
def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()


__all__ = ["WorkerSettings", "get_worker_settings"]
