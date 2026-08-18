from __future__ import annotations

import pytest
from pydantic import ValidationError

from cf_worker.config import WorkerSettings


def test_worker_secrets_are_not_exposed_by_repr() -> None:
    settings = WorkerSettings(
        worker_database_url="postgresql+asyncpg://worker:super-secret@localhost/db",
        celery_broker_url="redis://:broker-secret@localhost:6379/1",
    )
    rendered = repr(settings)
    assert "super-secret" not in rendered
    assert "broker-secret" not in rendered
    assert "**********" in rendered


def test_local_default_database_uses_explicit_ipv4_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKER_DATABASE_URL", raising=False)

    settings = WorkerSettings(_env_file=None)

    assert "@127.0.0.1:5432/" in settings.database_url


def test_wecom_proxy_url_is_available_to_notification_workers() -> None:
    settings = WorkerSettings(
        _env_file=None,
        wecom_proxy_url="socks5://127.0.0.1:10809",
    )

    assert settings.wecom_proxy_url == "socks5://127.0.0.1:10809"


def test_wecom_suite_credentials_are_all_or_none() -> None:
    with pytest.raises(ValidationError, match="must be configured together"):
        WorkerSettings(_env_file=None, wecom_suite_id="wwsuite123")

    settings = WorkerSettings(
        _env_file=None,
        wecom_suite_id="wwsuite123",
        wecom_suite_secret="test-only-suite-secret",  # noqa: S106 - fixture
    )
    assert settings.wecom_suite_secret is not None


def test_heartbeat_must_fit_inside_lease() -> None:
    with pytest.raises(ValidationError):
        WorkerSettings(outbox_lease_seconds=60, outbox_heartbeat_seconds=30)


def test_profile_retention_purge_interval_is_bounded() -> None:
    assert WorkerSettings(_env_file=None).profile_retention_purge_seconds == 3_600
    with pytest.raises(ValidationError):
        WorkerSettings(profile_retention_purge_seconds=59)


def test_platform_onboarding_retention_purge_interval_is_bounded() -> None:
    assert (
        WorkerSettings(_env_file=None).platform_onboarding_retention_purge_seconds
        == 3_600
    )
    with pytest.raises(ValidationError):
        WorkerSettings(platform_onboarding_retention_purge_seconds=59)
    with pytest.raises(ValidationError):
        WorkerSettings(platform_onboarding_retention_purge_seconds=86_401)


def test_content_import_poll_and_lease_are_bounded() -> None:
    settings = WorkerSettings(_env_file=None)
    assert settings.content_import_poll_seconds == 2
    assert settings.content_import_batch_size == 2
    assert settings.content_import_lease_seconds == 900
    with pytest.raises(ValidationError):
        WorkerSettings(content_import_poll_seconds=0.5)
    with pytest.raises(ValidationError):
        WorkerSettings(content_import_lease_seconds=30)


def test_production_rejects_local_worker_identity() -> None:
    with pytest.raises(ValidationError):
        WorkerSettings(app_env="production")
