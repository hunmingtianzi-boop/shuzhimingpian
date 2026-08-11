from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.errors import ApiError, ApiErrorBody, ApiErrorEnvelope, api_error_handler
from app.api.middleware import RequestContextMiddleware
from app.api.routes import (
    admin,
    auth,
    card_assets,
    crm,
    enterprise_content,
    enterprise_readiness,
    exports,
    health,
    knowledge_ops,
    members,
    platform,
    platform_llm,
    platform_onboarding,
    platform_operations,
    public_catalog,
    public_conversations,
    visitor_profiles,
    wecom,
    wecom_auth,
    wecom_callbacks,
    wecom_suite,
    workflow,
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.metrics import MetricsMiddleware, MetricsRegistry
from app.core.request_context import request_id_ctx

logger = structlog.get_logger(__name__)


def _database_connect_args(settings: Settings) -> dict[str, object]:
    if settings.database_url.startswith("postgresql+asyncpg"):
        return {
            "server_settings": {
                "statement_timeout": str(settings.database_statement_timeout_ms),
                "application_name": settings.app_name,
            }
        }
    return {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = app.state.settings
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        connect_args=_database_connect_args(settings),
    )
    redis = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.llm_timeout_seconds, connect=5.0),
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        follow_redirects=False,
    )
    wecom_http_client = (
        httpx.AsyncClient(
            proxy=settings.wecom_proxy_url,
            timeout=httpx.Timeout(settings.wecom_timeout_seconds, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=False,
            trust_env=False,
        )
        if settings.wecom_proxy_url
        else http_client
    )

    app.state.settings = settings
    app.state.database = engine
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.redis = redis
    app.state.http_client = http_client
    app.state.wecom_http_client = wecom_http_client
    app.state.ai_semaphore = asyncio.Semaphore(settings.llm_max_concurrency)
    app.state.ai_runtime_semaphores = {}
    app.state.ai_tasks = set()
    # Chat is intentionally built per request from the current active platform
    # profile. Tests may still inject ``rag_orchestrator`` as an explicit stub.
    app.state.rag_orchestrator = None
    try:
        yield
    finally:
        pending_tasks = tuple(app.state.ai_tasks)
        if pending_tasks:
            done, pending = await asyncio.wait(pending_tasks, timeout=10)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        if wecom_http_client is not http_client:
            await wecom_http_client.aclose()
        await http_client.aclose()
        await redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is not None:
        # Tests generally inject app.state directly; the explicit argument still
        # controls metadata and middleware without mutating process environment.
        runtime_settings = settings
    else:
        runtime_settings = get_settings()

    configure_logging(runtime_settings.log_level)
    api_docs_prefix = runtime_settings.api_prefix.rsplit("/", 1)[0]
    if runtime_settings.api_docs_enabled:
        docs_url = f"{api_docs_prefix}/docs"
        openapi_url = f"{api_docs_prefix}/openapi.json"
    elif runtime_settings.app_env == "production":
        docs_url = None
        openapi_url = None
    else:
        docs_url = "/docs"
        openapi_url = "/openapi.json"
    app = FastAPI(
        title="创非凡数智名片 API",
        version="0.1.0",
        docs_url=docs_url,
        openapi_url=openapi_url,
        redoc_url=None,
        root_path=runtime_settings.asgi_root_path,
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.public_card_base_url = runtime_settings.public_card_base_url
    app.state.require_staff_session_validation = True
    app.state.metrics = MetricsRegistry()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "X-CSRF-Token",
            "X-Request-Id",
        ],
        expose_headers=["ETag", "X-CSRF-Token", "X-Request-Id", "Retry-After"],
        max_age=600,
    )
    app.add_middleware(MetricsMiddleware, registry=app.state.metrics)
    app.add_middleware(RequestContextMiddleware)

    app.add_exception_handler(ApiError, api_error_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_details = [
            {"location": list(error["loc"]), "type": error["type"]} for error in exc.errors()
        ]
        payload = ApiErrorEnvelope(
            error=ApiErrorBody(
                code="VALIDATION_ERROR",
                message="请求参数不符合要求",
                details={"fields": safe_details},
                request_id=request_id_ctx.get(),
            )
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_request_error", error_type=type(exc).__name__)
        payload = ApiErrorEnvelope(
            error=ApiErrorBody(
                code="INTERNAL_ERROR",
                message="服务暂时无法处理该请求，请稍后重试",
                request_id=request_id_ctx.get(),
            )
        )
        return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))

    app.include_router(health.router, prefix=runtime_settings.api_prefix)
    app.include_router(auth.router, prefix=runtime_settings.api_prefix)
    app.include_router(admin.router, prefix=runtime_settings.api_prefix)
    app.include_router(card_assets.router, prefix=runtime_settings.api_prefix)
    app.include_router(enterprise_content.router, prefix=runtime_settings.api_prefix)
    app.include_router(enterprise_readiness.router, prefix=runtime_settings.api_prefix)
    app.include_router(members.router, prefix=runtime_settings.api_prefix)
    app.include_router(knowledge_ops.router, prefix=runtime_settings.api_prefix)
    app.include_router(platform.router, prefix=runtime_settings.api_prefix)
    app.include_router(platform_llm.router, prefix=runtime_settings.api_prefix)
    app.include_router(platform_onboarding.router, prefix=runtime_settings.api_prefix)
    app.include_router(platform_operations.router, prefix=runtime_settings.api_prefix)
    app.include_router(crm.router, prefix=runtime_settings.api_prefix)
    app.include_router(exports.router, prefix=runtime_settings.api_prefix)
    app.include_router(public_conversations.router, prefix=runtime_settings.api_prefix)
    app.include_router(public_catalog.router, prefix=runtime_settings.api_prefix)
    app.include_router(workflow.router, prefix=runtime_settings.api_prefix)
    app.include_router(visitor_profiles.router, prefix=runtime_settings.api_prefix)
    app.include_router(wecom.router, prefix=runtime_settings.api_prefix)
    app.include_router(wecom_auth.router, prefix=runtime_settings.api_prefix)
    app.include_router(wecom_callbacks.router, prefix=runtime_settings.api_prefix)
    app.include_router(wecom_suite.router, prefix=runtime_settings.api_prefix)
    return app


app = create_app()
