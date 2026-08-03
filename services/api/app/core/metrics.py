from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Mapping
from threading import Lock
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

HTTP_DURATION_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
AI_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0, 80.0)
FIRST_TOKEN_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 30.0)
COUNT_BUCKETS = (0.0, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0)
COVERAGE_BUCKETS = (0.0, 0.25, 0.5, 0.75, 1.0)

LabelSet = tuple[tuple[str, str], ...]
MetricKey = tuple[str, LabelSet]


def _labels(values: Mapping[str, object] | None = None) -> LabelSet:
    return tuple(sorted((key, str(value)) for key, value in (values or {}).items()))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_labels(labels: LabelSet, extra: tuple[str, str] | None = None) -> str:
    values = (*labels, extra) if extra is not None else labels
    if not values:
        return ""
    return "{" + ",".join(f'{key}="{_escape(value)}"' for key, value in values) + "}"


def _number(value: float) -> str:
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    if value.is_integer():
        return str(int(value))
    return format(value, ".12g")


class MetricsRegistry:
    """Small, dependency-free Prometheus registry with bounded-cardinality labels.

    The registry deliberately exposes only aggregate operational values. Tenant,
    company, card, visitor, question and request identifiers must never be labels.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: dict[MetricKey, float] = defaultdict(float)
        self._gauges: dict[MetricKey, float] = defaultdict(float)
        self._histograms: dict[MetricKey, tuple[tuple[float, ...], list[int], float, int]] = {}
        self._metadata: dict[str, tuple[str, str]] = {}
        self._in_flight = 0

    def counter(
        self,
        name: str,
        value: float = 1.0,
        *,
        labels: Mapping[str, object] | None = None,
        help_text: str,
    ) -> None:
        if value < 0:
            raise ValueError("counter increments must be non-negative")
        key = (name, _labels(labels))
        with self._lock:
            self._register(name, "counter", help_text)
            self._counters[key] += value

    def gauge(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, object] | None = None,
        help_text: str,
    ) -> None:
        key = (name, _labels(labels))
        with self._lock:
            self._register(name, "gauge", help_text)
            self._gauges[key] = value

    def histogram(
        self,
        name: str,
        value: float,
        *,
        buckets: tuple[float, ...],
        labels: Mapping[str, object] | None = None,
        help_text: str,
    ) -> None:
        if not math.isfinite(value) or value < 0:
            raise ValueError("histogram observations must be finite and non-negative")
        if not buckets or tuple(sorted(set(buckets))) != buckets:
            raise ValueError("histogram buckets must be unique and increasing")
        key = (name, _labels(labels))
        with self._lock:
            self._register(name, "histogram", help_text)
            current = self._histograms.get(key)
            if current is None:
                counts = [0] * len(buckets)
                total = 0.0
                count = 0
            else:
                current_buckets, counts, total, count = current
                if current_buckets != buckets:
                    raise ValueError(f"histogram {name} was registered with different buckets")
                counts = counts.copy()
            for index, boundary in enumerate(buckets):
                if value <= boundary:
                    counts[index] += 1
            self._histograms[key] = (buckets, counts, total + value, count + 1)

    def request_started(self) -> None:
        with self._lock:
            self._register(
                "cf_http_requests_in_flight",
                "gauge",
                "Current API HTTP requests being processed.",
            )
            self._in_flight += 1
            self._gauges[("cf_http_requests_in_flight", ())] = float(self._in_flight)

    def request_finished(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        labels = {
            "method": method,
            "route": route,
            "status_class": f"{max(0, status_code) // 100}xx",
        }
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            self._gauges[("cf_http_requests_in_flight", ())] = float(self._in_flight)
        self.counter(
            "cf_http_requests_total",
            labels=labels,
            help_text="API HTTP requests by route template and status class.",
        )
        self.histogram(
            "cf_http_request_duration_seconds",
            max(0.0, duration_seconds),
            buckets=HTTP_DURATION_BUCKETS,
            labels=labels,
            help_text="End-to-end API HTTP request duration in seconds.",
        )

    def observe_ai_result(
        self,
        *,
        provider: str,
        model: str,
        outcome: str,
        retrieval_mode: str,
        duration_seconds: float,
        model_seconds: float,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_cny: float,
        retrieval_count: int,
        citation_count: int,
        refusal_code: str | None,
        query_complexity: str = "not_applicable",
        confidence_band: str = "not_applicable",
        subquery_count: int = 0,
        coverage_ratio: float = 1.0,
    ) -> None:
        base_labels = {
            "provider": provider,
            "model": model,
            "outcome": outcome,
            "retrieval_mode": retrieval_mode,
        }
        self.counter(
            "cf_ai_requests_total",
            labels=base_labels,
            help_text="Completed AI requests by provider, model, outcome and retrieval mode.",
        )
        self.histogram(
            "cf_ai_request_duration_seconds",
            max(0.0, duration_seconds),
            buckets=AI_DURATION_BUCKETS,
            labels=base_labels,
            help_text="Full RAG request duration in seconds.",
        )
        self.histogram(
            "cf_ai_provider_duration_seconds",
            max(0.0, model_seconds),
            buckets=AI_DURATION_BUCKETS,
            labels={"provider": provider, "model": model, "outcome": outcome},
            help_text="Chat provider call duration in seconds.",
        )
        for token_type, value in (("input", input_tokens), ("output", output_tokens)):
            self.counter(
                "cf_ai_tokens_total",
                float(max(0, value)),
                labels={"provider": provider, "model": model, "type": token_type},
                help_text="AI provider tokens consumed by token type.",
            )
        self.counter(
            "cf_ai_estimated_cost_cny_total",
            max(0.0, estimated_cost_cny),
            labels={"provider": provider, "model": model},
            help_text="Estimated AI provider spend in CNY using configured token prices.",
        )
        self.histogram(
            "cf_rag_retrieval_results",
            float(max(0, retrieval_count)),
            buckets=COUNT_BUCKETS,
            labels={"mode": retrieval_mode, "outcome": outcome},
            help_text="Number of retrieved evidence chunks per RAG request.",
        )
        self.histogram(
            "cf_rag_citations",
            float(max(0, citation_count)),
            buckets=COUNT_BUCKETS,
            labels={"outcome": outcome},
            help_text="Number of validated citations returned per RAG request.",
        )
        if refusal_code is not None:
            self.counter(
                "cf_ai_refusals_total",
                labels={"code": refusal_code},
                help_text="Policy and evidence-gate refusals by bounded refusal code.",
            )
        rag_labels = {
            "complexity": query_complexity,
            "confidence": confidence_band,
            "outcome": outcome,
        }
        self.counter(
            "cf_rag_queries_total",
            labels=rag_labels,
            help_text="RAG requests by bounded query complexity, confidence and outcome.",
        )
        self.histogram(
            "cf_rag_subqueries",
            float(max(0, subquery_count)),
            buckets=COUNT_BUCKETS,
            labels={"complexity": query_complexity},
            help_text="Number of independently retrieved subqueries per RAG request.",
        )
        self.histogram(
            "cf_rag_coverage_ratio",
            min(1.0, max(0.0, coverage_ratio)),
            buckets=COVERAGE_BUCKETS,
            labels={"confidence": confidence_band},
            help_text="Share of planned retrieval subqueries with calibrated evidence.",
        )
        if refusal_code is not None and confidence_band == "low":
            self.counter(
                "cf_rag_low_confidence_blocks_total",
                labels={"code": refusal_code},
                help_text="Low-confidence answers blocked before reaching the visitor.",
            )

    def observe_ai_error(self, *, provider: str, model: str, category: str) -> None:
        self.counter(
            "cf_ai_errors_total",
            labels={"provider": provider, "model": model, "category": category},
            help_text="AI request failures by bounded internal category.",
        )

    def observe_first_token(self, *, source: str, duration_seconds: float) -> None:
        self.histogram(
            "cf_ai_time_to_first_content_seconds",
            max(0.0, duration_seconds),
            buckets=FIRST_TOKEN_BUCKETS,
            labels={"source": source},
            help_text="Visitor-observed time from SSE start to first answer content.",
        )

    def render(self) -> str:
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            histograms = {
                key: (buckets, counts.copy(), total, count)
                for key, (buckets, counts, total, count) in self._histograms.items()
            }
            metadata = dict(self._metadata)

        lines: list[str] = []
        for name in sorted(metadata):
            metric_type, help_text = metadata[name]
            lines.extend((f"# HELP {name} {help_text}", f"# TYPE {name} {metric_type}"))
            if metric_type == "counter":
                values = counters
            elif metric_type == "gauge":
                values = gauges
            else:
                values = {}
            for (metric_name, labels), value in sorted(values.items()):
                if metric_name == name:
                    lines.append(f"{name}{_format_labels(labels)} {_number(float(value))}")
            if metric_type == "histogram":
                for (metric_name, labels), value in sorted(histograms.items()):
                    if metric_name != name:
                        continue
                    buckets, counts, total, count = value
                    for boundary, bucket_count in zip(buckets, counts, strict=True):
                        lines.append(
                            f"{name}_bucket{_format_labels(labels, ('le', _number(boundary)))} "
                            f"{bucket_count}"
                        )
                    lines.append(
                        f"{name}_bucket{_format_labels(labels, ('le', '+Inf'))} {count}"
                    )
                    lines.append(f"{name}_sum{_format_labels(labels)} {_number(total)}")
                    lines.append(f"{name}_count{_format_labels(labels)} {count}")
        return "\n".join(lines) + "\n"

    def _register(self, name: str, metric_type: str, help_text: str) -> None:
        existing = self._metadata.get(name)
        candidate = (metric_type, help_text)
        if existing is not None and existing != candidate:
            raise ValueError(f"metric {name} was registered with incompatible metadata")
        self._metadata[name] = candidate


class MetricsMiddleware:
    """Measure the whole ASGI response, including streaming response bodies."""

    def __init__(self, app: ASGIApp, *, registry: MetricsRegistry) -> None:
        self.app = app
        self.registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500
        finished = False
        self.registry.request_started()

        def finish() -> None:
            nonlocal finished
            if finished:
                return
            finished = True
            route_object: Any = scope.get("route")
            route = getattr(route_object, "path", None) or "__unmatched__"
            application = scope.get("app")
            settings = getattr(getattr(application, "state", None), "settings", None)
            api_prefix = getattr(settings, "api_prefix", "")
            if route != "__unmatched__" and api_prefix and not route.startswith(api_prefix):
                route = f"{api_prefix}{route}"
            self.registry.request_finished(
                method=str(scope.get("method", "UNKNOWN")).upper(),
                route=str(route),
                status_code=status_code,
                duration_seconds=time.perf_counter() - started,
            )

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                finish()

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            finish()
