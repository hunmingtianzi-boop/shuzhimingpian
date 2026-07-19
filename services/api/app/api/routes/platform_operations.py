from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text

from app.api.dependencies import get_staff_principal
from app.api.errors import ApiError
from app.api.platform_schemas import (
    PlatformAuditListEnvelope,
    PlatformCompanyAggregateListEnvelope,
    PlatformEnterpriseDetailEnvelope,
    PlatformOverviewEnvelope,
    PlatformServiceHealthEnvelope,
    PlatformServiceHealthRecord,
    PlatformTaskListEnvelope,
)
from app.core.tokens import StaffPrincipal
from app.services.platform_store import PlatformActor, PlatformStore

router = APIRouter(prefix="/platform", tags=["Platform Administration"])
StaffDependency = Annotated[StaffPrincipal, Depends(get_staff_principal)]


def _store(request: Request) -> PlatformStore:
    return PlatformStore(
        request.app.state.session_factory,
        request.app.state.settings,
        public_card_base_url=getattr(request.app.state, "public_card_base_url", None),
    )


def _actor(principal: StaffPrincipal) -> PlatformActor:
    return PlatformActor(
        user_id=principal.user_id,
        tenant_id=principal.tenant_id,
        company_id=principal.company_id,
        session_id=principal.session_id,
        role=str(getattr(principal.role, "value", principal.role)),
    )


def _require_platform_admin(principal: StaffPrincipal) -> None:
    if str(getattr(principal.role, "value", principal.role)) != "platform_admin":
        raise ApiError(403, "FORBIDDEN", "仅平台管理员可访问平台运营数据")


@router.get(
    "/overview",
    response_model=PlatformOverviewEnvelope,
    operation_id="getPlatformOverview",
)
async def get_platform_overview(
    request: Request,
    principal: StaffDependency,
) -> PlatformOverviewEnvelope:
    _require_platform_admin(principal)
    record = await _store(request).get_overview(actor=_actor(principal))
    return PlatformOverviewEnvelope(data=record)


@router.get(
    "/enterprises/{company_id}",
    response_model=PlatformEnterpriseDetailEnvelope,
    operation_id="getPlatformEnterpriseDetail",
)
async def get_platform_enterprise_detail(
    company_id: uuid.UUID,
    request: Request,
    principal: StaffDependency,
) -> PlatformEnterpriseDetailEnvelope:
    _require_platform_admin(principal)
    record = await _store(request).get_enterprise_detail(
        actor=_actor(principal),
        company_id=company_id,
    )
    return PlatformEnterpriseDetailEnvelope(data=record)


@router.get(
    "/company-aggregates",
    response_model=PlatformCompanyAggregateListEnvelope,
    operation_id="listPlatformCompanyAggregates",
)
async def list_platform_company_aggregates(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlatformCompanyAggregateListEnvelope:
    _require_platform_admin(principal)
    records, total = await _store(request).list_company_aggregates(
        actor=_actor(principal), limit=limit, offset=offset
    )
    return PlatformCompanyAggregateListEnvelope(
        data=records, total=total, limit=limit, offset=offset
    )


@router.get(
    "/tasks",
    response_model=PlatformTaskListEnvelope,
    operation_id="listPlatformTasks",
)
async def list_platform_tasks(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlatformTaskListEnvelope:
    _require_platform_admin(principal)
    records, total = await _store(request).list_tasks(
        actor=_actor(principal), limit=limit, offset=offset
    )
    return PlatformTaskListEnvelope(data=records, total=total, limit=limit, offset=offset)


@router.get(
    "/audit",
    response_model=PlatformAuditListEnvelope,
    operation_id="listPlatformAudit",
)
async def list_platform_audit(
    request: Request,
    principal: StaffDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlatformAuditListEnvelope:
    _require_platform_admin(principal)
    records, total = await _store(request).list_audit(
        actor=_actor(principal), limit=limit, offset=offset
    )
    return PlatformAuditListEnvelope(data=records, total=total, limit=limit, offset=offset)


async def _probe(
    service: Literal["database", "redis", "object_storage", "worker"],
    operation: Awaitable[object],
) -> PlatformServiceHealthRecord:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(operation, timeout=1.5)
        return PlatformServiceHealthRecord(
            service=service,
            status="healthy",
            checked_at=datetime.now(UTC),
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        )
    except Exception:  # noqa: BLE001 - health projection must isolate failures
        return PlatformServiceHealthRecord(
            service=service,
            status="unavailable",
            checked_at=datetime.now(UTC),
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
            error_code=f"{service.upper()}_UNAVAILABLE",
        )


async def _database_ping(request: Request) -> None:
    async with request.app.state.session_factory() as session:
        await session.execute(text("SELECT 1"))


async def _http_ready_ping(request: Request, url: str) -> None:
    response = await request.app.state.http_client.get(url, timeout=1.5)
    response.raise_for_status()


@router.get(
    "/health",
    response_model=PlatformServiceHealthEnvelope,
    operation_id="getPlatformServiceHealth",
)
async def get_platform_service_health(
    request: Request,
    principal: StaffDependency,
) -> PlatformServiceHealthEnvelope:
    _require_platform_admin(principal)
    object_storage_url = (
        request.app.state.settings.object_storage_endpoint.rstrip("/")
        + "/minio/health/ready"
    )
    database, redis, object_storage, worker = await asyncio.gather(
        _probe("database", _database_ping(request)),
        _probe("redis", request.app.state.redis.ping()),
        _probe(
            "object_storage",
            _http_ready_ping(request, object_storage_url),
        ),
        _probe(
            "worker",
            _http_ready_ping(request, "http://worker:8020/health/ready"),
        ),
    )
    now = datetime.now(UTC)
    return PlatformServiceHealthEnvelope(
        data=[
            PlatformServiceHealthRecord(
                service="api", status="healthy", checked_at=now, latency_ms=0
            ),
            database,
            redis,
            object_storage,
            worker,
        ]
    )


__all__ = ["router"]
