from __future__ import annotations

import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from ipaddress import ip_address
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.pii import PiiCipher, PiiCipherError
from app.db.models import MembershipRole, PlatformLLMProfile
from app.db.session import set_rls_context
from app.services.audit import append_audit

PLATFORM_LLM_WRITE_LOCK = "platform_llm_profiles:write"


class PlatformLLMActorLike(Protocol):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class PlatformLLMActor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    company_id: uuid.UUID
    session_id: uuid.UUID
    role: str


@dataclass(frozen=True, slots=True)
class CreateProfileInput:
    name: str
    provider: str
    base_url: str
    api_key: str = field(repr=False)
    model: str
    purpose: Literal["chat_main"] = "chat_main"
    thinking: Literal["enabled", "disabled"] = "disabled"
    reasoning_effort: Literal["high", "max"] | None = None
    timeout_seconds: float = 30
    max_retries: int = 2
    max_concurrency: int = 20
    max_output_tokens: int = 32_768
    temperature: float = 0.1
    daily_budget_cny: float = 100
    input_price_cny_per_million: float = 0
    output_price_cny_per_million: float = 0
    allow_general_answers: bool = False
    faq_fast_path_enabled: bool = False
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class UpdateProfileInput:
    name: str
    provider: str
    base_url: str
    model: str
    expected_version: int
    api_key: str | None = field(default=None, repr=False)
    purpose: Literal["chat_main"] = "chat_main"
    thinking: Literal["enabled", "disabled"] = "disabled"
    reasoning_effort: Literal["high", "max"] | None = None
    timeout_seconds: float = 30
    max_retries: int = 2
    max_concurrency: int = 20
    max_output_tokens: int = 32_768
    temperature: float = 0.1
    daily_budget_cny: float = 100
    input_price_cny_per_million: float = 0
    output_price_cny_per_million: float = 0
    allow_general_answers: bool = False
    faq_fast_path_enabled: bool = False
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ActivateProfileInput:
    expected_version: int
    expected_active_profile_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class PlatformLLMProfileView:
    id: uuid.UUID
    name: str
    purpose: Literal["chat_main"]
    provider: str
    base_url: str
    model: str
    thinking: Literal["enabled", "disabled"]
    reasoning_effort: Literal["high", "max"] | None
    timeout_seconds: float
    max_retries: int
    max_concurrency: int
    max_output_tokens: int
    temperature: float
    daily_budget_cny: float
    input_price_cny_per_million: float
    output_price_cny_per_million: float
    allow_general_answers: bool
    faq_fast_path_enabled: bool
    enabled: bool
    is_active: bool
    version: int
    key_configured: bool
    key_hint: str | None
    last_test_status: Literal["untested", "succeeded", "failed"]
    last_test_latency_ms: int | None
    last_tested_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EffectiveChatConfig:
    profile_id: uuid.UUID | None
    profile_name: str
    provider: str
    base_url: str
    api_key: SecretStr = field(repr=False)
    model: str
    thinking: Literal["enabled", "disabled"]
    reasoning_effort: Literal["high", "max"]
    timeout_seconds: float
    max_retries: int
    max_concurrency: int
    max_output_tokens: int
    temperature: float
    daily_budget_cny: float
    input_price_cny_per_million: float
    output_price_cny_per_million: float
    enabled: bool
    source: Literal["database", "environment"]
    version: int
    allow_general_answers: bool = False
    faq_fast_path_enabled: bool = False
    updated_at: datetime | None = None

    def apply_to_settings(self, settings: Settings) -> Settings:
        """Build a request-local settings copy without touching import settings."""

        return settings.model_copy(
            update={
                "llm_provider": self.provider,
                "llm_base_url": self.base_url,
                "llm_api_key": self.api_key,
                "llm_model": self.model,
                "llm_thinking": self.thinking,
                "llm_reasoning_effort": self.reasoning_effort,
                "llm_timeout_seconds": self.timeout_seconds,
                "llm_max_retries": self.max_retries,
                "llm_max_concurrency": self.max_concurrency,
                "llm_max_output_tokens": self.max_output_tokens,
                "llm_temperature": self.temperature,
                "llm_input_price_cny_per_million": self.input_price_cny_per_million,
                "llm_output_price_cny_per_million": self.output_price_cny_per_million,
                "model_daily_budget_cny": self.daily_budget_cny,
                "llm_allow_general_answers": self.allow_general_answers,
                "rag_faq_fast_path_enabled": self.faq_fast_path_enabled,
            }
        )


@dataclass(frozen=True, slots=True)
class PlatformLLMProbeResult:
    ok: bool
    profile_id: uuid.UUID | None
    tested_version: int
    provider: str
    model: str
    latency_ms: int
    error_code: str | None = None


class LLMRuntimeUnavailable(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__("main Chat LLM configuration is unavailable")
        self.code = code


def key_hint(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    if len(normalized) <= 4:
        return "••••"
    return f"••••{normalized[-4:]}"


def validate_provider_base_url(value: str, *, app_env: str) -> str:
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise ValueError("provider base URL is invalid") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("provider base URL is invalid")

    hostname = parsed.hostname.casefold().rstrip(".")
    if app_env in {"staging", "production"}:
        if parsed.scheme != "https":
            raise ValueError("provider base URL must use HTTPS")
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ValueError("provider base URL host is not allowed")
        try:
            address = ip_address(hostname)
        except ValueError:
            _require_global_dns_resolution(hostname, parsed.port or 443)
        else:
            if not address.is_global:
                raise ValueError("provider base URL host is not allowed")

    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if parsed.port is not None:
        netloc = f"{hostname}:{parsed.port}"
    normalized_path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme.casefold(), netloc, normalized_path, "", ""))


def _require_global_dns_resolution(hostname: str, port: int) -> None:
    try:
        results = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("provider base URL host could not be resolved") from exc
    addresses = set()
    for family, _socket_type, _protocol, _canonical_name, sockaddr in results:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        try:
            addresses.add(ip_address(sockaddr[0].split("%", 1)[0]))
        except (IndexError, ValueError) as exc:
            raise ValueError("provider base URL host resolved to an invalid address") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("provider base URL host is not allowed")


def environment_chat_config(settings: Settings) -> EffectiveChatConfig:
    if settings.llm_api_key is None or not settings.llm_api_key.get_secret_value().strip():
        raise LLMRuntimeUnavailable("api_key_missing")
    try:
        base_url = validate_provider_base_url(settings.llm_base_url, app_env=settings.app_env)
    except ValueError as exc:
        raise LLMRuntimeUnavailable("configuration_invalid") from exc
    return EffectiveChatConfig(
        profile_id=None,
        profile_name="环境变量配置",
        provider=settings.llm_provider,
        base_url=base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        thinking=settings.llm_thinking,
        reasoning_effort=settings.llm_reasoning_effort,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        max_concurrency=settings.llm_max_concurrency,
        max_output_tokens=settings.llm_max_output_tokens,
        temperature=settings.llm_temperature,
        daily_budget_cny=settings.model_daily_budget_cny,
        input_price_cny_per_million=settings.llm_input_price_cny_per_million,
        output_price_cny_per_million=settings.llm_output_price_cny_per_million,
        enabled=True,
        source="environment",
        version=0,
        allow_general_answers=settings.llm_allow_general_answers,
        faq_fast_path_enabled=settings.rag_faq_fast_path_enabled,
    )


def database_chat_config(
    row: PlatformLLMProfile,
    *,
    settings: Settings,
    require_enabled: bool = True,
    api_key_override: SecretStr | None = None,
) -> EffectiveChatConfig:
    if require_enabled and not row.enabled:
        raise LLMRuntimeUnavailable("configuration_disabled")
    if api_key_override is not None:
        plaintext = api_key_override.get_secret_value()
    else:
        if row.api_key_ciphertext is None:
            raise LLMRuntimeUnavailable("api_key_missing")
        try:
            plaintext = PiiCipher.from_settings(settings).decrypt(row.api_key_ciphertext)
        except PiiCipherError as exc:
            raise LLMRuntimeUnavailable("configuration_invalid") from exc
    if not plaintext.strip():
        raise LLMRuntimeUnavailable("configuration_invalid")
    try:
        base_url = validate_provider_base_url(row.base_url, app_env=settings.app_env)
    except ValueError as exc:
        raise LLMRuntimeUnavailable("configuration_invalid") from exc
    return EffectiveChatConfig(
        profile_id=row.id,
        profile_name=row.name,
        provider=row.provider,
        base_url=base_url,
        api_key=SecretStr(plaintext),
        model=row.model,
        thinking=cast(Literal["enabled", "disabled"], row.thinking),
        reasoning_effort=cast(
            Literal["high", "max"], row.reasoning_effort or settings.llm_reasoning_effort
        ),
        timeout_seconds=float(row.timeout_seconds),
        max_retries=row.max_retries,
        max_concurrency=row.max_concurrency,
        max_output_tokens=row.max_output_tokens,
        temperature=float(row.temperature),
        daily_budget_cny=float(row.daily_budget_cny),
        input_price_cny_per_million=float(row.input_price_cny_per_million),
        output_price_cny_per_million=float(row.output_price_cny_per_million),
        enabled=row.enabled,
        source="database",
        version=row.version,
        allow_general_answers=row.allow_general_answers,
        faq_fast_path_enabled=row.faq_fast_path_enabled,
        updated_at=row.updated_at,
    )


async def resolve_effective_chat_config(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> EffectiveChatConfig:
    """Resolve the selected profile on every request; only zero rows may fall back.

    The active-profile uniqueness constraint lets one ordered query distinguish
    between an active profile, an inactive/misconfigured profile, and an empty
    table.  Chat traffic takes this path for every new answer, so avoiding the
    former active-query plus count-query sequence removes a database round trip
    from the latency-critical path.
    """

    async with session_factory() as session, session.begin():
        profile = await session.scalar(
            select(PlatformLLMProfile)
            .order_by(
                PlatformLLMProfile.is_active.desc(),
                PlatformLLMProfile.updated_at.desc(),
                PlatformLLMProfile.id,
            )
            .limit(1)
        )
    if profile is not None and profile.is_active:
        return database_chat_config(profile, settings=settings)
    if profile is not None:
        raise LLMRuntimeUnavailable("active_configuration_missing")
    return environment_chat_config(settings)


async def is_chat_available(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> bool:
    try:
        await resolve_effective_chat_config(session_factory, settings)
    except LLMRuntimeUnavailable:
        return False
    return True


async def probe_openai_models(
    http_client: httpx.AsyncClient,
    config: EffectiveChatConfig,
) -> PlatformLLMProbeResult:
    started = time.perf_counter()
    error_code: str | None = None
    try:
        async with http_client.stream(
            "GET",
            f"{config.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {config.api_key.get_secret_value()}"},
            timeout=httpx.Timeout(min(config.timeout_seconds, 10.0)),
            follow_redirects=False,
        ) as response:
            status_code = response.status_code
        if 200 <= status_code < 300:
            ok = True
        else:
            ok = False
            error_code = _probe_error_code(status_code)
    except httpx.TimeoutException:
        ok = False
        error_code = "provider_timeout"
    except httpx.RequestError:
        ok = False
        error_code = "provider_unavailable"
    return PlatformLLMProbeResult(
        ok=ok,
        profile_id=config.profile_id,
        tested_version=config.version,
        provider=config.provider,
        model=config.model,
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        error_code=error_code,
    )


def _probe_error_code(status_code: int) -> str:
    if status_code in {401, 403}:
        return "provider_authentication_failed"
    if status_code == 429:
        return "provider_rate_limited"
    if 300 <= status_code < 400:
        return "provider_redirect_rejected"
    if status_code >= 500:
        return "provider_unavailable"
    return "provider_request_rejected"


class PlatformLLMProfileService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._http = http_client
        self._cipher = PiiCipher.from_settings(settings)

    async def list_profiles(
        self,
        *,
        actor: PlatformLLMActorLike,
    ) -> list[PlatformLLMProfileView]:
        self._require_platform(actor)
        async with self._sessions() as session, session.begin():
            await self._set_actor_scope(session, actor)
            rows = (
                await session.scalars(
                    select(PlatformLLMProfile).order_by(
                        PlatformLLMProfile.is_active.desc(),
                        func.lower(PlatformLLMProfile.name),
                        PlatformLLMProfile.id,
                    )
                )
            ).all()
        return [self._view(row) for row in rows]

    async def get_profile(
        self,
        *,
        actor: PlatformLLMActorLike,
        profile_id: uuid.UUID,
    ) -> PlatformLLMProfileView:
        self._require_platform(actor)
        async with self._sessions() as session, session.begin():
            await self._set_actor_scope(session, actor)
            row = await session.scalar(
                select(PlatformLLMProfile).where(PlatformLLMProfile.id == profile_id)
            )
        if row is None:
            raise ApiError(404, "RESOURCE_NOT_FOUND", "LLM 配置不存在")
        return self._view(row)

    async def create_profile(
        self,
        *,
        actor: PlatformLLMActorLike,
        body: CreateProfileInput,
        trace_id: str | None,
    ) -> PlatformLLMProfileView:
        self._require_platform(actor)
        values = self._validated_values(body)
        secret = body.api_key.strip()
        if not secret:
            raise ApiError(422, "LLM_API_KEY_REQUIRED", "新增配置必须提供 API Key")
        try:
            async with self._sessions() as session, session.begin():
                await self._set_actor_scope(session, actor)
                await self._lock_writes(session)
                if await self._name_exists(session, values["name"]):
                    raise self._name_conflict()
                profile_count = int(
                    await session.scalar(select(func.count(PlatformLLMProfile.id))) or 0
                )
                if (
                    profile_count
                    and await session.scalar(
                        select(PlatformLLMProfile.id).where(PlatformLLMProfile.is_active.is_(True))
                    )
                    is None
                ):
                    raise ApiError(
                        409,
                        "LLM_ACTIVE_PROFILE_MISSING",
                        "已有 LLM 配置但主配置状态异常，请先修复数据",
                    )
                row = PlatformLLMProfile(
                    id=uuid.uuid4(),
                    **values,
                    api_key_ciphertext=self._cipher.encrypt(secret),
                    api_key_key_ref=self._cipher.key_ref,
                    api_key_hint=key_hint(secret),
                    is_active=profile_count == 0,
                    version=1,
                    last_test_status="untested",
                    last_test_latency_ms=None,
                    last_tested_at=None,
                    updated_by=actor.user_id,
                )
                session.add(row)
                await session.flush()
                await self._audit(
                    session,
                    actor=actor,
                    action="platform.llm_profile.create",
                    row=row,
                    trace_id=trace_id,
                    event_data={"key_changed": True},
                )
                await session.refresh(row)
                return self._view(row)
        except IntegrityError as exc:
            raise self._integrity_conflict(exc) from exc

    async def update_profile(
        self,
        *,
        actor: PlatformLLMActorLike,
        profile_id: uuid.UUID,
        body: UpdateProfileInput,
        trace_id: str | None,
    ) -> PlatformLLMProfileView:
        self._require_platform(actor)
        values = self._validated_values(body)
        try:
            async with self._sessions() as session, session.begin():
                await self._set_actor_scope(session, actor)
                await self._lock_writes(session)
                row = await session.scalar(
                    select(PlatformLLMProfile)
                    .where(PlatformLLMProfile.id == profile_id)
                    .with_for_update()
                )
                if row is None:
                    raise ApiError(404, "RESOURCE_NOT_FOUND", "LLM 配置不存在")
                self._require_version(row, body.expected_version)
                if await self._name_exists(session, values["name"], exclude_id=row.id):
                    raise self._name_conflict()

                secret = (body.api_key or "").strip()
                key_changed = bool(secret)
                if key_changed:
                    row.api_key_ciphertext = self._cipher.encrypt(secret)
                    row.api_key_key_ref = self._cipher.key_ref
                    row.api_key_hint = key_hint(secret)
                if values["enabled"]:
                    self._require_usable_key(row)
                for field_name, value in values.items():
                    setattr(row, field_name, value)
                row.version += 1
                row.updated_by = actor.user_id
                await session.flush()
                await self._audit(
                    session,
                    actor=actor,
                    action="platform.llm_profile.update",
                    row=row,
                    trace_id=trace_id,
                    event_data={"key_changed": key_changed},
                )
                await session.refresh(row)
                return self._view(row)
        except IntegrityError as exc:
            raise self._integrity_conflict(exc) from exc

    async def activate_profile(
        self,
        *,
        actor: PlatformLLMActorLike,
        profile_id: uuid.UUID,
        body: ActivateProfileInput,
        trace_id: str | None,
    ) -> PlatformLLMProfileView:
        self._require_platform(actor)
        async with self._sessions() as session, session.begin():
            await self._set_actor_scope(session, actor)
            await self._lock_writes(session)
            target = await session.scalar(
                select(PlatformLLMProfile)
                .where(PlatformLLMProfile.id == profile_id)
                .with_for_update()
            )
            if target is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "LLM 配置不存在")
            self._require_version(target, body.expected_version)
            current = await session.scalar(
                select(PlatformLLMProfile)
                .where(PlatformLLMProfile.is_active.is_(True))
                .with_for_update()
            )
            current_id = current.id if current is not None else None
            if current_id != body.expected_active_profile_id:
                raise ApiError(
                    409,
                    "LLM_ACTIVE_PROFILE_CONFLICT",
                    "当前主配置已变化，请刷新后重试",
                )
            if not target.enabled:
                raise ApiError(409, "LLM_PROFILE_DISABLED", "停用配置不能设为主配置")
            self._require_usable_key(target)
            if current_id == target.id:
                return self._view(target)

            if current is not None:
                current.is_active = False
                current.version += 1
                current.updated_by = actor.user_id
                await session.flush()
            target.is_active = True
            target.version += 1
            target.updated_by = actor.user_id
            await session.flush()
            await self._audit(
                session,
                actor=actor,
                action="platform.llm_profile.activate",
                row=target,
                trace_id=trace_id,
                event_data={
                    "previous_active_profile_id": str(current_id) if current_id else None,
                },
            )
            await session.refresh(target)
            return self._view(target)

    async def test_profile_connection(
        self,
        *,
        actor: PlatformLLMActorLike,
        profile_id: uuid.UUID,
        trace_id: str | None,
        api_key_override: SecretStr | None = None,
    ) -> PlatformLLMProbeResult:
        self._require_platform(actor)
        async with self._sessions() as session, session.begin():
            await self._set_actor_scope(session, actor)
            row = await session.scalar(
                select(PlatformLLMProfile).where(PlatformLLMProfile.id == profile_id)
            )
            if row is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "LLM 配置不存在")
            config = database_chat_config(
                row,
                settings=self._settings,
                require_enabled=False,
                api_key_override=api_key_override,
            )
        result = await probe_openai_models(self._http, config)
        async with self._sessions() as session, session.begin():
            await self._set_actor_scope(session, actor)
            current = await session.scalar(
                select(PlatformLLMProfile)
                .where(PlatformLLMProfile.id == profile_id)
                .with_for_update()
            )
            if current is None:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "LLM 配置不存在")
            if current.version == result.tested_version:
                current.last_test_status = "succeeded" if result.ok else "failed"
                current.last_test_latency_ms = result.latency_ms
                current.last_tested_at = datetime.now(UTC)
                await session.flush()
            await self._audit(
                session,
                actor=actor,
                action="platform.llm_profile.test",
                row=current,
                trace_id=trace_id,
                event_data={
                    "ok": result.ok,
                    "error_code": result.error_code,
                    "tested_version": result.tested_version,
                    "latency_ms": result.latency_ms,
                },
            )
        return result

    def _validated_values(self, body: CreateProfileInput | UpdateProfileInput) -> dict[str, object]:
        name = body.name.strip()
        provider = body.provider.strip()
        model = body.model.strip()
        if not name or len(name) > 120:
            raise ApiError(422, "LLM_PROFILE_NAME_INVALID", "配置名称不能为空且不超过 120 字")
        if not provider or len(provider) > 80:
            raise ApiError(422, "LLM_PROVIDER_INVALID", "Provider 不能为空且不超过 80 字")
        if not model or len(model) > 160:
            raise ApiError(422, "LLM_MODEL_INVALID", "模型名称不能为空且不超过 160 字")
        if len(body.base_url.strip()) > 2_048:
            raise ApiError(422, "LLM_BASE_URL_INVALID", "Provider Base URL 长度超过限制")
        if not 2 <= body.timeout_seconds <= 120:
            raise ApiError(422, "LLM_TIMEOUT_INVALID", "超时时间必须在 2 到 120 秒之间")
        if not 0 <= body.max_retries <= 5:
            raise ApiError(422, "LLM_RETRIES_INVALID", "重试次数必须在 0 到 5 之间")
        if not 1 <= body.max_concurrency <= 500:
            raise ApiError(422, "LLM_CONCURRENCY_INVALID", "并发数必须在 1 到 500 之间")
        if not 128 <= body.max_output_tokens <= 65_536:
            raise ApiError(422, "LLM_OUTPUT_TOKENS_INVALID", "最大输出必须在 128 到 65536 之间")
        if not 0 <= body.temperature <= 2:
            raise ApiError(422, "LLM_TEMPERATURE_INVALID", "Temperature 必须在 0 到 2 之间")
        if body.thinking == "enabled" and body.temperature != 0.1:
            raise ApiError(422, "LLM_THINKING_TEMPERATURE_INVALID", "思考模式下温度必须为 0.1")
        if body.daily_budget_cny < 0:
            raise ApiError(422, "LLM_BUDGET_INVALID", "每日预算不能为负数")
        if body.input_price_cny_per_million < 0 or body.output_price_cny_per_million < 0:
            raise ApiError(422, "LLM_PRICE_INVALID", "模型价格不能为负数")
        try:
            base_url = validate_provider_base_url(body.base_url, app_env=self._settings.app_env)
        except ValueError as exc:
            raise ApiError(422, "LLM_BASE_URL_INVALID", "Provider Base URL 不安全或无效") from exc
        return {
            "name": name,
            "purpose": body.purpose,
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "thinking": body.thinking,
            "reasoning_effort": body.reasoning_effort,
            "timeout_seconds": Decimal(str(body.timeout_seconds)),
            "max_retries": body.max_retries,
            "max_concurrency": body.max_concurrency,
            "max_output_tokens": body.max_output_tokens,
            "temperature": Decimal(str(body.temperature)),
            "daily_budget_cny": Decimal(str(body.daily_budget_cny)),
            "input_price_cny_per_million": Decimal(str(body.input_price_cny_per_million)),
            "output_price_cny_per_million": Decimal(str(body.output_price_cny_per_million)),
            "allow_general_answers": body.allow_general_answers,
            "faq_fast_path_enabled": body.faq_fast_path_enabled,
            "enabled": body.enabled,
        }

    async def _name_exists(
        self,
        session: AsyncSession,
        name: str,
        *,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        statement = select(PlatformLLMProfile.id).where(
            func.lower(func.btrim(PlatformLLMProfile.name)) == name.casefold()
        )
        if exclude_id is not None:
            statement = statement.where(PlatformLLMProfile.id != exclude_id)
        return await session.scalar(statement) is not None

    def _require_usable_key(self, row: PlatformLLMProfile) -> None:
        if row.api_key_ciphertext is None:
            raise ApiError(409, "LLM_PROFILE_KEY_MISSING", "启用配置必须先保存 API Key")
        try:
            value = self._cipher.decrypt(row.api_key_ciphertext)
        except PiiCipherError as exc:
            raise ApiError(409, "LLM_PROFILE_CREDENTIAL_INVALID", "配置密钥无法解密") from exc
        if not value.strip():
            raise ApiError(409, "LLM_PROFILE_CREDENTIAL_INVALID", "配置密钥无效")

    @staticmethod
    def _require_platform(actor: PlatformLLMActorLike) -> None:
        if actor.role != MembershipRole.PLATFORM_ADMIN.value:
            raise ApiError(403, "FORBIDDEN", "仅平台管理员可管理 LLM 配置")

    @staticmethod
    def _require_version(row: PlatformLLMProfile, expected_version: int) -> None:
        if row.version != expected_version:
            raise ApiError(
                409,
                "LLM_PROFILE_VERSION_CONFLICT",
                "LLM 配置已被更新，请刷新后重试",
            )

    @staticmethod
    async def _lock_writes(session: AsyncSession) -> None:
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": PLATFORM_LLM_WRITE_LOCK},
        )

    @staticmethod
    async def _set_actor_scope(session: AsyncSession, actor: PlatformLLMActorLike) -> None:
        await set_rls_context(
            session,
            tenant_id=actor.tenant_id,
            company_id=actor.company_id,
            actor_user_id=actor.user_id,
            actor_session_id=actor.session_id,
        )

    @staticmethod
    def _name_conflict() -> ApiError:
        return ApiError(409, "LLM_PROFILE_NAME_CONFLICT", "LLM 配置名称已存在")

    @staticmethod
    def _integrity_conflict(exc: IntegrityError) -> ApiError:
        detail = str(exc.orig).casefold()
        if "uq_platform_llm_profiles_name_normalized" in detail:
            return PlatformLLMProfileService._name_conflict()
        return ApiError(
            409,
            "LLM_PROFILE_WRITE_CONFLICT",
            "LLM 配置状态已变化，请刷新后重试",
        )

    @staticmethod
    def _view(row: PlatformLLMProfile) -> PlatformLLMProfileView:
        return PlatformLLMProfileView(
            id=row.id,
            name=row.name,
            purpose=cast(Literal["chat_main"], row.purpose),
            provider=row.provider,
            base_url=row.base_url,
            model=row.model,
            thinking=cast(Literal["enabled", "disabled"], row.thinking),
            reasoning_effort=cast(Literal["high", "max"] | None, row.reasoning_effort),
            timeout_seconds=float(row.timeout_seconds),
            max_retries=row.max_retries,
            max_concurrency=row.max_concurrency,
            max_output_tokens=row.max_output_tokens,
            temperature=float(row.temperature),
            daily_budget_cny=float(row.daily_budget_cny),
            input_price_cny_per_million=float(row.input_price_cny_per_million),
            output_price_cny_per_million=float(row.output_price_cny_per_million),
            allow_general_answers=row.allow_general_answers,
            faq_fast_path_enabled=row.faq_fast_path_enabled,
            enabled=row.enabled,
            is_active=row.is_active,
            version=row.version,
            key_configured=row.api_key_ciphertext is not None,
            key_hint=row.api_key_hint,
            last_test_status=cast(Literal["untested", "succeeded", "failed"], row.last_test_status),
            last_test_latency_ms=row.last_test_latency_ms,
            last_tested_at=row.last_tested_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    async def _audit(
        session: AsyncSession,
        *,
        actor: PlatformLLMActorLike,
        action: str,
        row: PlatformLLMProfile,
        trace_id: str | None,
        event_data: dict[str, object],
    ) -> None:
        await append_audit(
            session,
            tenant_id=actor.tenant_id,
            company_id=actor.company_id,
            actor_user_id=actor.user_id,
            action=action,
            resource_type="platform_llm_profile",
            resource_id=row.id,
            trace_id=trace_id,
            event_data={
                "profile_id": str(row.id),
                "profile_name": row.name,
                "provider": row.provider,
                "model": row.model,
                "allow_general_answers": row.allow_general_answers,
                "faq_fast_path_enabled": row.faq_fast_path_enabled,
                "enabled": row.enabled,
                "is_active": row.is_active,
                "version": row.version,
                **event_data,
            },
        )


__all__ = [
    "ActivateProfileInput",
    "CreateProfileInput",
    "EffectiveChatConfig",
    "LLMRuntimeUnavailable",
    "PlatformLLMActor",
    "PlatformLLMActorLike",
    "PlatformLLMProbeResult",
    "PlatformLLMProfileService",
    "PlatformLLMProfileView",
    "UpdateProfileInput",
    "database_chat_config",
    "environment_chat_config",
    "is_chat_available",
    "key_hint",
    "probe_openai_models",
    "resolve_effective_chat_config",
    "validate_provider_base_url",
]
