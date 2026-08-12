from __future__ import annotations

import asyncio
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from celery.signals import worker_ready, worker_shutdown
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from cf_worker.config import WorkerSettings, get_worker_settings

_READY = threading.Event()
_SERVER: ThreadingHTTPServer | None = None
_SERVER_THREAD: threading.Thread | None = None


async def readiness_probe(settings: WorkerSettings) -> tuple[bool, dict[str, Any]]:
    async def database_probe() -> bool:
        engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args={"server_settings": {"statement_timeout": "3000"}},
        )
        try:
            async with engine.connect() as connection:
                return bool(
                    await connection.scalar(
                        text(
                            """
                            SELECT has_schema_privilege(current_user, 'app', 'USAGE')
                               AND has_function_privilege(
                                 current_user,
                                 'app.claim_outbox_events(text,integer,integer)',
                                 'EXECUTE'
                               )
                               AND has_function_privilege(
                                 current_user,
                                 'app.claim_knowledge_import_items(text,integer,integer)',
                                 'EXECUTE'
                               )
                               AND has_table_privilege(
                                 current_user, 'outbox_events', 'SELECT'
                               )
                               AND has_table_privilege(
                                 current_user, 'knowledge_import_items', 'SELECT,UPDATE'
                               )
                            """
                        )
                    )
                )
        finally:
            await engine.dispose()

    async def broker_probe() -> bool:
        redis = Redis.from_url(
            settings.broker_url,
            socket_connect_timeout=settings.worker_health_timeout_seconds,
            socket_timeout=settings.worker_health_timeout_seconds,
        )
        try:
            return bool(await redis.ping())
        finally:
            await redis.aclose()

    try:
        async with asyncio.timeout(settings.worker_health_timeout_seconds):
            database_ok, redis_ok = await asyncio.gather(database_probe(), broker_probe())
    except Exception:
        # Health responses and logs must not expose connection strings or provider errors.
        database_ok = False
        redis_ok = False
    ready = _READY.is_set() and database_ok and redis_ok
    return ready, {
        "status": "ready" if ready else "not_ready",
        "database": database_ok,
        "broker": redis_ok,
        "worker": _READY.is_set(),
    }


class _HealthHandler(BaseHTTPRequestHandler):
    server_version = "cf-worker-health"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 - stdlib HTTP handler contract
        if self.path == "/health/live":
            self._respond(HTTPStatus.OK, {"status": "live"})
            return
        if self.path == "/health/ready":
            ready, payload = asyncio.run(readiness_probe(get_worker_settings()))
            self._respond(HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE, payload)
            return
        self._respond(HTTPStatus.NOT_FOUND, {"status": "not_found"})

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _respond(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError):
            return


@worker_ready.connect
def start_health_server(**_kwargs: object) -> None:
    global _SERVER, _SERVER_THREAD
    if _SERVER is not None:
        return
    settings = get_worker_settings()
    _READY.set()
    _SERVER = ThreadingHTTPServer(
        (settings.worker_health_host, settings.worker_health_port),
        _HealthHandler,
    )
    _SERVER_THREAD = threading.Thread(
        target=_SERVER.serve_forever,
        name="worker-health",
        daemon=True,
    )
    _SERVER_THREAD.start()


@worker_shutdown.connect
def stop_health_server(**_kwargs: object) -> None:
    global _SERVER, _SERVER_THREAD
    _READY.clear()
    if _SERVER is not None:
        _SERVER.shutdown()
        _SERVER.server_close()
    if _SERVER_THREAD is not None:
        _SERVER_THREAD.join(timeout=5)
    _SERVER = None
    _SERVER_THREAD = None


__all__ = ["readiness_probe", "start_health_server", "stop_health_server"]
