from __future__ import annotations

import json
from functools import lru_cache
from ipaddress import ip_network
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Secrets stay wrapped in ``SecretStr`` so accidental model dumps and log calls
    cannot reveal provider or signing keys.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../../.env", "../../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "cf-ai-card"
    api_prefix: str = "/api/v1"
    asgi_root_path: str = ""
    api_docs_enabled: bool = False
    log_level: str = "INFO"
    metrics_bearer_token: SecretStr | None = None
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:4173", "http://localhost:4173"]
    )
    public_card_base_url: str = "http://127.0.0.1:4173"
    allow_insecure_public_card_http: bool = False

    database_url: str = (
        "postgresql+asyncpg://cf_ai_card_app:change-me-app-local-only@localhost:5432/cf_ai_card"
    )
    migration_database_url: str | None = None
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_max_overflow: int = Field(default=20, ge=0, le=200)
    database_statement_timeout_ms: int = Field(default=8_000, ge=500, le=60_000)
    redis_url: str = "redis://localhost:6379/0"

    object_storage_endpoint: str = "http://127.0.0.1:9000"
    object_storage_region: str = "local"
    object_storage_bucket: str = "cf-ai-card-local"
    object_storage_access_key: str = "minioadmin"
    object_storage_secret_key: SecretStr = SecretStr("change-me-local-only")
    object_storage_secure: bool = False

    jwt_signing_key: SecretStr = SecretStr("replace-with-at-least-32-random-bytes")
    field_encryption_key: SecretStr = SecretStr("replace-with-kms-backed-key")
    field_encryption_key_ref: str = Field(default="local-v1", min_length=1, max_length=128)
    field_encryption_previous_keys: SecretStr | None = None
    trusted_proxy_cidrs: list[str] = Field(default_factory=list)
    visitor_token_ttl_seconds: int = Field(default=7_200, ge=300, le=86_400)
    profile_link_token_ttl_seconds: int = Field(
        default=15_552_000, ge=86_400, le=31_536_000
    )
    visitor_profile_retention_days: int = Field(default=365, ge=1, le=730)
    access_token_ttl_seconds: int = Field(default=900, ge=300, le=3_600)
    refresh_token_ttl_seconds: int = Field(default=604_800, ge=3_600, le=7_776_000)
    staff_login_max_failures: int = Field(default=5, ge=3, le=20)
    staff_login_lock_seconds: int = Field(default=900, ge=60, le=86_400)
    staff_login_ip_rate_limit_per_minute: int = Field(default=30, ge=1, le=1_000)
    staff_login_account_rate_limit_per_minute: int = Field(default=10, ge=1, le=300)
    staff_refresh_ip_rate_limit_per_minute: int = Field(default=60, ge=1, le=1_000)
    staff_refresh_cookie_name: str = Field(
        default="cf_staff_refresh",
        pattern=r"^[A-Za-z0-9_-]{3,80}$",
    )
    staff_csrf_cookie_name: str = Field(
        default="cf_staff_csrf",
        pattern=r"^[A-Za-z0-9_-]{3,80}$",
    )
    staff_auth_cookie_secure: bool = False
    staff_auth_cookie_samesite: Literal["strict", "lax"] = "strict"
    admin_bootstrap_tenant_slug: str | None = None
    admin_bootstrap_account: str | None = None
    admin_bootstrap_password: SecretStr | None = None

    llm_provider: str = "deepseek"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: SecretStr | None = None
    llm_model: str = "deepseek-v4-flash"
    llm_thinking: Literal["enabled", "disabled"] = "disabled"
    llm_reasoning_effort: Literal["high", "max"] = "high"
    llm_timeout_seconds: float = Field(default=30.0, ge=2, le=120)
    llm_max_output_tokens: int = Field(default=1_000, ge=128, le=8_192)
    llm_temperature: float = Field(default=0.1, ge=0, le=2)
    llm_max_concurrency: int = Field(default=20, ge=1, le=500)
    llm_queue_timeout_seconds: float = Field(default=3.0, ge=0.1, le=30)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    llm_input_price_cny_per_million: float = Field(default=0.0, ge=0)
    llm_output_price_cny_per_million: float = Field(default=0.0, ge=0)

    embedding_provider: str | None = None
    embedding_base_url: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_model: str | None = None
    embedding_dimension: int = Field(default=1_024, ge=64, le=4_096)
    embedding_timeout_seconds: float = Field(default=20.0, ge=2, le=120)

    # Enterprise WeChat (WeCom) pilot connector. Provider credentials remain
    # environment-backed while identity bindings and callbacks are encrypted,
    # tenant-scoped database records.
    wecom_corp_id: str | None = None
    wecom_agent_id: int | None = Field(default=None, ge=1)
    wecom_app_secret: SecretStr | None = None
    wecom_tenant_id: UUID | None = None
    wecom_company_id: UUID | None = None
    wecom_api_base_url: str = "https://qyapi.weixin.qq.com"
    # Optional dedicated egress proxy for WeCom API calls. Keeping this
    # separate from the shared HTTP client prevents AI and storage traffic
    # from depending on a temporary provider-whitelist tunnel.
    wecom_proxy_url: str | None = None
    wecom_oauth_redirect_uri: str | None = None
    wecom_oauth_state_ttl_seconds: int = Field(default=600, ge=120, le=1_800)
    wecom_callback_token: SecretStr | None = None
    wecom_callback_encoding_aes_key: SecretStr | None = None
    wecom_timeout_seconds: float = Field(default=8.0, ge=2, le=30)

    # Enterprise WeChat third-party provider application.  These values are
    # intentionally separate from the self-built pilot credentials above so a
    # release can keep the pilot online while the provider application is
    # being tested and certified.  No customer corporation credential belongs
    # in environment variables; each authorization is encrypted in PostgreSQL.
    wecom_auth_mode: Literal["auto", "self_built", "third_party"] = "auto"
    wecom_suite_id: str | None = None
    wecom_suite_secret: SecretStr | None = None
    wecom_suite_callback_token: SecretStr | None = None
    wecom_suite_callback_encoding_aes_key: SecretStr | None = None
    wecom_suite_callback_corp_id: str | None = None
    wecom_suite_install_redirect_uri: str | None = None
    wecom_suite_oauth_redirect_uri: str | None = None
    wecom_suite_success_redirect_uri: str | None = None
    wecom_suite_auth_type: Literal["formal", "test"] = "test"
    wecom_suite_userinfo_path: str = "/cgi-bin/service/auth/getuserinfo3rd"

    retrieval_top_k: int = Field(default=8, ge=1, le=30)
    retrieval_context_k: int = Field(default=5, ge=1, le=10)
    retrieval_vector_weight: float = Field(default=0.65, ge=0, le=1)
    retrieval_min_vector_score: float = Field(default=0.55, ge=-1, le=1)
    retrieval_min_lexical_score: float = Field(default=0.08, ge=0, le=1)
    llm_allow_general_answers: bool = True
    rag_faq_fast_path_enabled: bool = False
    rag_faq_similarity_threshold: float = Field(default=0.92, ge=0, le=1)
    rag_faq_cache_ttl_seconds: int = Field(default=60, ge=5, le=3_600)
    rag_faq_max_question_chars: int = Field(default=180, ge=20, le=1_000)

    public_chat_rate_limit_per_minute: int = Field(default=10, ge=1, le=300)
    public_chat_ip_card_rate_limit_per_minute: int = Field(default=20, ge=1, le=1_000)
    public_visit_ip_card_rate_limit_per_minute: int = Field(default=60, ge=1, le=2_000)
    max_message_chars: int = Field(default=2_000, ge=100, le=10_000)
    max_conversation_messages: int = Field(default=30, ge=2, le=200)
    model_daily_budget_cny: float = Field(default=100.0, gt=0)

    @field_validator("api_prefix")
    @classmethod
    def normalize_api_prefix(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/")

    @field_validator("asgi_root_path")
    @classmethod
    def normalize_asgi_root_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or normalized == "/":
            return ""
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        return normalized.rstrip("/")

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def parse_trusted_proxy_cidrs(cls, value: object) -> object:
        if isinstance(value, str) and not value.lstrip().startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: list[str]) -> list[str]:
        for item in value:
            try:
                ip_network(item, strict=False)
            except ValueError as exc:
                raise ValueError(f"invalid trusted proxy CIDR: {item}") from exc
        return value

    @field_validator("field_encryption_key_ref")
    @classmethod
    def validate_field_encryption_key_ref(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:/-"
            for character in normalized
        ):
            raise ValueError("FIELD_ENCRYPTION_KEY_REF has an invalid format")
        return normalized

    @field_validator("object_storage_bucket")
    @classmethod
    def validate_object_storage_bucket(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not 3 <= len(normalized) <= 63 or not all(
            character.islower() or character.isdigit() or character in {"-", "."}
            for character in normalized
        ):
            raise ValueError("OBJECT_STORAGE_BUCKET has an invalid format")
        if normalized[0] in {"-", "."} or normalized[-1] in {"-", "."} or ".." in normalized:
            raise ValueError("OBJECT_STORAGE_BUCKET has an invalid format")
        return normalized

    @field_validator(
        "llm_api_key",
        "embedding_api_key",
        "admin_bootstrap_password",
        "field_encryption_previous_keys",
        "metrics_bearer_token",
        "wecom_app_secret",
        "wecom_callback_token",
        "wecom_callback_encoding_aes_key",
        "wecom_suite_secret",
        "wecom_suite_callback_token",
        "wecom_suite_callback_encoding_aes_key",
        mode="before",
    )
    @classmethod
    def empty_secret_is_unconfigured(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("wecom_agent_id", mode="before")
    @classmethod
    def empty_wecom_agent_id_is_unconfigured(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("wecom_tenant_id", "wecom_company_id", mode="before")
    @classmethod
    def empty_wecom_scope_is_unconfigured(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "wecom_corp_id",
        "wecom_oauth_redirect_uri",
        "wecom_suite_id",
        "wecom_suite_callback_corp_id",
        "wecom_suite_install_redirect_uri",
        "wecom_suite_oauth_redirect_uri",
        "wecom_suite_success_redirect_uri",
        mode="before",
    )
    @classmethod
    def empty_wecom_text_is_unconfigured(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator("admin_bootstrap_tenant_slug", "admin_bootstrap_account", mode="before")
    @classmethod
    def empty_bootstrap_text_is_unconfigured(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @field_validator(
        "embedding_provider",
        "embedding_base_url",
        "embedding_model",
        mode="before",
    )
    @classmethod
    def empty_embedding_text_is_unconfigured(cls, value: object) -> object:
        """Treat Compose's empty optional environment values as absent.

        Docker Compose expands an unset ``${NAME:-}`` to an empty string.  These
        fields are optional as a group so lexical-only retrieval can start
        without an embedding endpoint; preserving an empty model name would
        instead make RAG initialization fail during application startup.
        """
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        public_base = self.public_card_base_url.strip().rstrip("/")
        parsed_public_base = urlsplit(public_base)
        if (
            parsed_public_base.scheme.casefold() not in {"http", "https"}
            or not parsed_public_base.netloc
            or parsed_public_base.username
            or parsed_public_base.password
            or parsed_public_base.path
            or parsed_public_base.query
            or parsed_public_base.fragment
        ):
            raise ValueError("PUBLIC_CARD_BASE_URL must be an absolute origin without /c")
        if (
            parsed_public_base.scheme.casefold() == "http"
            and parsed_public_base.hostname not in {"localhost", "127.0.0.1"}
            and not self.allow_insecure_public_card_http
        ):
            raise ValueError(
                "remote HTTP PUBLIC_CARD_BASE_URL requires "
                "ALLOW_INSECURE_PUBLIC_CARD_HTTP=true"
            )
        self.public_card_base_url = public_base

        if self.app_env in {"staging", "production"}:
            signing_key = self.jwt_signing_key.get_secret_value()
            if signing_key.startswith("replace-") or len(signing_key) < 32:
                raise ValueError(
                    "JWT_SIGNING_KEY must be a strong secret outside local development"
                )
            encryption_key = self.field_encryption_key.get_secret_value()
            if encryption_key.startswith("replace-") or len(encryption_key) < 32:
                raise ValueError(
                    "FIELD_ENCRYPTION_KEY must be a strong secret outside local development"
                )
            if self.field_encryption_key_ref.casefold().startswith("local"):
                raise ValueError(
                    "FIELD_ENCRYPTION_KEY_REF must identify a managed key outside local "
                    "development"
                )
            if self.field_encryption_previous_keys is not None:
                try:
                    previous_keys = json.loads(
                        self.field_encryption_previous_keys.get_secret_value()
                    )
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "FIELD_ENCRYPTION_PREVIOUS_KEYS must be a secret JSON object"
                    ) from exc
                if not isinstance(previous_keys, dict) or not all(
                    isinstance(reference, str)
                    and isinstance(secret, str)
                    and len(secret) >= 32
                    and not secret.startswith("replace-")
                    for reference, secret in previous_keys.items()
                ):
                    raise ValueError(
                        "FIELD_ENCRYPTION_PREVIOUS_KEYS must contain strong referenced keys"
                    )
            if self.app_env == "production" and not self.staff_auth_cookie_secure:
                raise ValueError("STAFF_AUTH_COOKIE_SECURE must be true in production")
            if self.metrics_bearer_token is None:
                raise ValueError(
                    "METRICS_BEARER_TOKEN is required outside local development"
                )
            if (
                self.object_storage_access_key == "minioadmin"
                or self.object_storage_secret_key.get_secret_value().startswith("change-me")
            ):
                raise ValueError(
                    "OBJECT_STORAGE credentials must be configured outside local development"
                )
            if not self.llm_api_key:
                raise ValueError("LLM_API_KEY is required outside local development")
            if (
                self.llm_input_price_cny_per_million <= 0
                or self.llm_output_price_cny_per_million <= 0
            ):
                raise ValueError("LLM token prices must be configured outside local development")
        if self.embedding_provider and not (
            self.embedding_base_url and self.embedding_api_key and self.embedding_model
        ):
            raise ValueError(
                "EMBEDDING_BASE_URL, EMBEDDING_API_KEY and EMBEDDING_MODEL are required "
                "when EMBEDDING_PROVIDER is enabled"
            )
        wecom_core = (self.wecom_corp_id, self.wecom_agent_id, self.wecom_app_secret)
        if any(value is not None for value in wecom_core) and not all(
            value is not None for value in wecom_core
        ):
            raise ValueError(
                "WECOM_CORP_ID, WECOM_AGENT_ID and WECOM_APP_SECRET must be configured together"
            )
        wecom_callback = (
            self.wecom_callback_token,
            self.wecom_callback_encoding_aes_key,
        )
        if any(value is not None for value in wecom_callback) and not all(
            value is not None for value in wecom_callback
        ):
            raise ValueError(
                "WECOM_CALLBACK_TOKEN and WECOM_CALLBACK_ENCODING_AES_KEY must be "
                "configured together"
            )
        wecom_scope = (self.wecom_tenant_id, self.wecom_company_id)
        if any(value is not None for value in wecom_scope) and not all(
            value is not None for value in wecom_scope
        ):
            raise ValueError(
                "WECOM_TENANT_ID and WECOM_COMPANY_ID must be configured together"
            )
        if self.wecom_oauth_redirect_uri and not all(
            value is not None for value in wecom_core
        ):
            raise ValueError(
                "WeCom OAuth requires WECOM_CORP_ID, WECOM_AGENT_ID and WECOM_APP_SECRET"
            )
        if any(wecom_callback) and not all(
            value is not None for value in (*wecom_core, *wecom_scope)
        ):
            raise ValueError(
                "WeCom callbacks require core credentials and a tenant/company scope"
            )
        wecom_suite_core = (self.wecom_suite_id, self.wecom_suite_secret)
        if self.wecom_suite_secret is not None and self.wecom_suite_id is None:
            raise ValueError(
                "WECOM_SUITE_SECRET requires WECOM_SUITE_ID"
            )
        wecom_suite_callback = (
            self.wecom_suite_callback_token,
            self.wecom_suite_callback_encoding_aes_key,
        )
        if any(value is not None for value in wecom_suite_callback) and not all(
            value is not None for value in wecom_suite_callback
        ):
            raise ValueError(
                "WECOM_SUITE_CALLBACK_TOKEN and WECOM_SUITE_CALLBACK_ENCODING_AES_KEY "
                "must be configured together"
            )
        if any(value is not None for value in wecom_suite_callback) and not self.wecom_suite_id:
            raise ValueError("WeCom suite callbacks require SuiteID")
        if self.wecom_auth_mode == "self_built" and not all(
            value is not None for value in wecom_core
        ):
            raise ValueError("WECOM_AUTH_MODE=self_built requires self-built credentials")
        if self.wecom_auth_mode == "third_party" and not all(
            value is not None for value in wecom_suite_core
        ):
            raise ValueError("WECOM_AUTH_MODE=third_party requires suite credentials")
        wecom_base = urlsplit(self.wecom_api_base_url.strip().rstrip("/"))
        if (
            wecom_base.scheme.casefold() != "https"
            or not wecom_base.netloc
            or wecom_base.username
            or wecom_base.password
            or wecom_base.path
            or wecom_base.query
            or wecom_base.fragment
        ):
            raise ValueError("WECOM_API_BASE_URL must be an HTTPS origin")
        self.wecom_api_base_url = self.wecom_api_base_url.strip().rstrip("/")
        if self.wecom_oauth_redirect_uri:
            oauth_redirect = urlsplit(self.wecom_oauth_redirect_uri)
            local_redirect = oauth_redirect.hostname in {"localhost", "127.0.0.1"}
            if (
                oauth_redirect.scheme.casefold() not in {"http", "https"}
                or not oauth_redirect.netloc
                or oauth_redirect.username
                or oauth_redirect.password
                or (oauth_redirect.scheme.casefold() != "https" and not local_redirect)
            ):
                raise ValueError(
                    "WECOM_OAUTH_REDIRECT_URI must use HTTPS outside local development"
                )
        for field_name, value in (
            ("WECOM_SUITE_INSTALL_REDIRECT_URI", self.wecom_suite_install_redirect_uri),
            ("WECOM_SUITE_OAUTH_REDIRECT_URI", self.wecom_suite_oauth_redirect_uri),
            ("WECOM_SUITE_SUCCESS_REDIRECT_URI", self.wecom_suite_success_redirect_uri),
        ):
            if not value:
                continue
            parsed = urlsplit(value)
            local_uri = parsed.hostname in {"localhost", "127.0.0.1"}
            if (
                parsed.scheme.casefold() not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or (parsed.scheme.casefold() != "https" and not local_uri)
            ):
                raise ValueError(f"{field_name} must use HTTPS outside local development")
        suite_path = self.wecom_suite_userinfo_path.strip()
        if not suite_path.startswith("/cgi-bin/service/") or any(
            value in suite_path for value in ("?", "#", "\\")
        ):
            raise ValueError("WECOM_SUITE_USERINFO_PATH is invalid")
        self.wecom_suite_userinfo_path = suite_path
        bootstrap_values = (
            self.admin_bootstrap_tenant_slug,
            self.admin_bootstrap_account,
            self.admin_bootstrap_password,
        )
        if any(value is not None for value in bootstrap_values) and not all(
            value is not None for value in bootstrap_values
        ):
            raise ValueError(
                "ADMIN_BOOTSTRAP_TENANT_SLUG, ADMIN_BOOTSTRAP_ACCOUNT and "
                "ADMIN_BOOTSTRAP_PASSWORD must be configured together"
            )
        if self.admin_bootstrap_tenant_slug and not all(
            character.islower() or character.isdigit() or character == "-"
            for character in self.admin_bootstrap_tenant_slug
        ):
            raise ValueError("ADMIN_BOOTSTRAP_TENANT_SLUG has an invalid format")
        if self.admin_bootstrap_account and not 3 <= len(self.admin_bootstrap_account) <= 200:
            raise ValueError("ADMIN_BOOTSTRAP_ACCOUNT length is invalid")
        if self.admin_bootstrap_password:
            password = self.admin_bootstrap_password.get_secret_value()
            if not 12 <= len(password) <= 200:
                raise ValueError("ADMIN_BOOTSTRAP_PASSWORD must contain 12-200 characters")
        if self.staff_refresh_cookie_name == self.staff_csrf_cookie_name:
            raise ValueError("staff refresh and CSRF cookie names must be different")
        if "*" in self.cors_allowed_origins and self.app_env in {"staging", "production"}:
            raise ValueError("credentialed CORS cannot use a wildcard origin")
        if self.llm_thinking == "enabled" and self.llm_temperature != 0.1:
            # DeepSeek V4 ignores sampling temperature in thinking mode. Rejecting a
            # misleading production configuration is safer than silently accepting it.
            raise ValueError("LLM_TEMPERATURE must remain at its neutral default in thinking mode")
        if self.retrieval_context_k > self.retrieval_top_k:
            raise ValueError("RETRIEVAL_CONTEXT_K cannot exceed RETRIEVAL_TOP_K")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
