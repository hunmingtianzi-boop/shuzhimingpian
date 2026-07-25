from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.errors import ApiError
from app.api.workflow_schemas import TopicAnalysisItem, TopicAnalysisView
from app.core.config import Settings
from app.core.redaction import redact_sensitive_text
from app.db.models import Card, Conversation, Message, MessageRole, MessageStatus
from app.db.session import set_rls_context
from app.services.audit import append_audit
from app.services.platform_llm_profiles import resolve_effective_chat_config
from app.services.workflow_store import WorkflowScope

TOPIC_ANALYSIS_PROMPT_VERSION = "conversation-topic-analysis-v1"
TOPIC_ANALYSIS_SYSTEM_PROMPT = """
你是企业数智名片的客户问题分析助手。输入内容是经过脱敏的用户问题。

任务：
1. 将语义相近的问题归入同一个业务话题，最多 8 个话题。
2. topics 数组必须与输入 questions 等长，并按原顺序为每个问题填写一个话题。
3. topic 使用简洁、明确的中文业务名称，长度 2-16 个汉字或字符。
4. summary 用 1-3 句话概括用户最关注的问题和可行动的内容改进方向。

限制：
- 只根据输入问题归类，不补充企业事实，不判断访客身份。
- 不输出电话、邮箱、微信号、身份证、密钥或其他个人敏感值。
- 不复制长段用户原文，不提供销售承诺或自动决策。
- 输出必须是单个 JSON 对象，只包含 summary 和 topics。
- topics 只包含话题名称，不添加序号、说明或其他字段。
""".strip()
_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
_MAX_ANALYZED_QUESTIONS = 200
_MAX_QUESTION_CHARS = 280
_SPACE_PATTERN = re.compile(r"\s+")


class _TopicProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    summary: str = Field(min_length=1, max_length=800)
    topics: list[str] = Field(default_factory=list, max_length=_MAX_ANALYZED_QUESTIONS)


@dataclass(frozen=True, slots=True)
class TopicQuestion:
    id: uuid.UUID
    content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class TopicGeneration:
    summary: str
    assignments: tuple[tuple[int, str], ...]
    provider: str
    model: str
    latency_ms: int


class TopicAnalysisProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._client = client

    async def generate(
        self,
        questions: Sequence[TopicQuestion],
        *,
        trace_id: str | None = None,
    ) -> TopicGeneration:
        api_key = self._settings.llm_api_key
        if api_key is None:
            raise ApiError(503, "LLM_API_KEY_MISSING", "AI 话题分析服务尚未配置")
        input_payload = json.dumps(
            {
                "questions": [
                    redact_sensitive_text(question.content).content[:_MAX_QUESTION_CHARS]
                    for question in questions
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request_payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "messages": [
                {"role": "system", "content": TOPIC_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": input_payload},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": min(self._settings.llm_max_output_tokens, 2_000),
            "stream": False,
            "thinking": {"type": self._settings.llm_thinking},
        }
        if self._settings.llm_thinking != "enabled":
            request_payload["temperature"] = min(self._settings.llm_temperature, 0.2)
        elif self._settings.llm_reasoning_effort:
            request_payload["reasoning_effort"] = self._settings.llm_reasoning_effort

        started = time.perf_counter()
        response: httpx.Response | None = None
        for attempt in range(self._settings.llm_max_retries + 1):
            try:
                response = await self._client.post(
                    f"{self._settings.llm_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                        **({"X-Request-Id": trace_id} if trace_id else {}),
                    },
                    json=request_payload,
                    timeout=self._settings.llm_timeout_seconds,
                )
            except (httpx.HTTPError, TimeoutError) as exc:
                if attempt >= self._settings.llm_max_retries:
                    raise ApiError(
                        503,
                        "TOPIC_ANALYSIS_PROVIDER_UNAVAILABLE",
                        "AI 话题分析服务暂不可用",
                    ) from exc
                await asyncio.sleep(min(0.1 * (2**attempt), 1.0))
                continue
            if response.status_code < 400:
                break
            if response.status_code not in {408, 409, 429} and response.status_code < 500:
                raise ApiError(
                    503,
                    "TOPIC_ANALYSIS_PROVIDER_REJECTED",
                    "AI 话题分析服务拒绝了请求",
                )
            if attempt >= self._settings.llm_max_retries:
                raise ApiError(
                    503,
                    "TOPIC_ANALYSIS_PROVIDER_UNAVAILABLE",
                    "AI 话题分析服务暂不可用",
                )
            await asyncio.sleep(min(0.1 * (2**attempt), 1.0))
        if response is None:
            raise ApiError(
                503,
                "TOPIC_ANALYSIS_PROVIDER_UNAVAILABLE",
                "AI 话题分析服务暂不可用",
            )

        try:
            payload: Any = response.json()
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            parsed = _TopicProviderResponse.model_validate_json(_strip_json_fence(content))
            return TopicGeneration(
                summary=redact_sensitive_text(parsed.summary).content,
                assignments=tuple(
                    (index, topic)
                    for index, topic in enumerate(parsed.topics)
                ),
                provider=self._settings.llm_provider,
                model=str(payload.get("model") or self._settings.llm_model),
                latency_ms=max(0, round((time.perf_counter() - started) * 1_000)),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ApiError(
                503,
                "TOPIC_ANALYSIS_RESPONSE_INVALID",
                "AI 话题分析返回格式无效",
            ) from exc


class TopicAnalysisService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        http_client: httpx.AsyncClient,
        redis: Redis | None,
        *,
        semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._http_client = http_client
        self._redis = redis
        self._semaphore = semaphore

    async def get(
        self,
        *,
        scope: WorkflowScope,
        period_days: int,
    ) -> TopicAnalysisView:
        questions, question_count = await self._questions(
            scope=scope,
            period_days=period_days,
        )
        if question_count == 0:
            return _empty_view(period_days)
        input_hash = _question_hash(questions)
        cached = await self._cached(scope=scope, period_days=period_days)
        if cached is None:
            return TopicAnalysisView(
                status="not_generated",
                period_days=period_days,
                question_count=question_count,
                analyzed_question_count=len(questions),
            )
        cached_hash, view = cached
        return view.model_copy(
            update={
                "status": "ready" if cached_hash == input_hash else "stale",
                "question_count": question_count,
            }
        )

    async def analyze(
        self,
        *,
        scope: WorkflowScope,
        period_days: int,
        trace_id: str | None,
    ) -> TopicAnalysisView:
        questions, question_count = await self._questions(
            scope=scope,
            period_days=period_days,
        )
        if question_count == 0:
            return _empty_view(period_days)
        config = await resolve_effective_chat_config(self._sessions, self._settings)
        runtime_settings = config.apply_to_settings(self._settings)
        provider = TopicAnalysisProvider(runtime_settings, self._http_client)
        if self._semaphore is None:
            generation = await provider.generate(questions, trace_id=trace_id)
        else:
            async with self._semaphore:
                generation = await provider.generate(questions, trace_id=trace_id)
        view = _build_view(
            questions=questions,
            question_count=question_count,
            period_days=period_days,
            generation=generation,
        )
        input_hash = _question_hash(questions)
        await self._cache(
            scope=scope,
            period_days=period_days,
            input_hash=input_hash,
            view=view,
        )
        await self._audit(
            scope=scope,
            period_days=period_days,
            input_hash=input_hash,
            view=view,
            latency_ms=generation.latency_ms,
            trace_id=trace_id,
        )
        return view

    async def _questions(
        self,
        *,
        scope: WorkflowScope,
        period_days: int,
    ) -> tuple[list[TopicQuestion], int]:
        cutoff = datetime.now(UTC) - timedelta(days=period_days)
        owner_filter = (
            (Card.owner_user_id == scope.actor_user_id,)
            if scope.is_card_owner
            else ()
        )
        filters = (
            Message.tenant_id == scope.tenant_id,
            Message.company_id == scope.company_id,
            Message.role == MessageRole.USER,
            Message.status == MessageStatus.COMPLETED,
            Message.created_at >= cutoff,
            *owner_filter,
        )
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
            total = int(
                await session.scalar(
                    select(func.count(Message.id))
                    .select_from(Message)
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(*filters)
                )
                or 0
            )
            rows = (
                await session.execute(
                    select(Message.id, Message.content, Message.created_at)
                    .select_from(Message)
                    .join(Conversation, Conversation.id == Message.conversation_id)
                    .join(Card, Card.id == Conversation.card_id)
                    .where(*filters)
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(_MAX_ANALYZED_QUESTIONS)
                )
            ).all()
        questions = []
        for message_id, content, created_at in reversed(rows):
            redacted = redact_sensitive_text(str(content)).content.strip()
            if redacted:
                questions.append(
                    TopicQuestion(
                        id=message_id,
                        content=redacted[:_MAX_QUESTION_CHARS],
                        created_at=created_at,
                    )
                )
        return questions, total

    async def _cached(
        self,
        *,
        scope: WorkflowScope,
        period_days: int,
    ) -> tuple[str, TopicAnalysisView] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(_cache_key(scope, period_days))
        except RedisError:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            input_hash = str(payload["input_hash"])
            view = TopicAnalysisView.model_validate(payload["data"])
            return input_hash, view
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _cache(
        self,
        *,
        scope: WorkflowScope,
        period_days: int,
        input_hash: str,
        view: TopicAnalysisView,
    ) -> None:
        if self._redis is None:
            return
        payload = json.dumps(
            {
                "input_hash": input_hash,
                "data": view.model_dump(mode="json"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            await self._redis.setex(
                _cache_key(scope, period_days),
                _CACHE_TTL_SECONDS,
                payload,
            )
        except RedisError:
            return

    async def _audit(
        self,
        *,
        scope: WorkflowScope,
        period_days: int,
        input_hash: str,
        view: TopicAnalysisView,
        latency_ms: int,
        trace_id: str | None,
    ) -> None:
        async with self._sessions() as session, session.begin():
            await set_rls_context(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
            )
            await append_audit(
                session,
                tenant_id=scope.tenant_id,
                company_id=scope.company_id,
                actor_user_id=scope.actor_user_id,
                action="conversation_topics.analyzed",
                resource_type="conversation_topics",
                resource_id=None,
                trace_id=trace_id,
                event_data={
                    "period_days": period_days,
                    "question_count": view.question_count,
                    "analyzed_question_count": view.analyzed_question_count,
                    "topic_count": len(view.topics),
                    "provider": view.provider,
                    "model": view.model,
                    "input_hash": input_hash,
                    "latency_ms": latency_ms,
                },
            )


def _build_view(
    *,
    questions: Sequence[TopicQuestion],
    question_count: int,
    period_days: int,
    generation: TopicGeneration,
) -> TopicAnalysisView:
    question_by_id = {str(question.id): question for question in questions}
    assigned: dict[str, str] = {}
    for question_index, topic in generation.assignments:
        if question_index < 0 or question_index >= len(questions):
            continue
        message_id = str(questions[question_index].id)
        if message_id in assigned:
            continue
        assigned[message_id] = _safe_topic(topic)
    for message_id in question_by_id:
        assigned.setdefault(message_id, "其他问题")

    counts = Counter(assigned.values())
    if len(counts) > 8:
        keep = {topic for topic, _count in counts.most_common(7)}
        assigned = {
            message_id: topic if topic in keep else "其他问题"
            for message_id, topic in assigned.items()
        }
        counts = Counter(assigned.values())

    grouped: dict[str, list[str]] = defaultdict(list)
    for message_id, topic in assigned.items():
        grouped[topic].append(question_by_id[message_id].content)
    analyzed_count = max(1, len(questions))
    topics = [
        TopicAnalysisItem(
            topic=topic,
            count=count,
            share=round(count / analyzed_count, 4),
            sample_questions=grouped[topic][:2],
        )
        for topic, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]
    return TopicAnalysisView(
        status="ready",
        generated_at=datetime.now(UTC),
        period_days=period_days,
        question_count=question_count,
        analyzed_question_count=len(questions),
        summary=redact_sensitive_text(generation.summary).content[:600],
        topics=topics,
        provider=generation.provider,
        model=generation.model,
    )


def _safe_topic(value: str) -> str:
    redacted = redact_sensitive_text(value).content
    compact = _SPACE_PATTERN.sub(" ", redacted).strip(" \t\r\n,，。；;：:")
    return (compact or "其他问题")[:40]


def _empty_view(period_days: int) -> TopicAnalysisView:
    return TopicAnalysisView(
        status="empty",
        period_days=period_days,
        question_count=0,
        analyzed_question_count=0,
    )


def _question_hash(questions: Sequence[TopicQuestion]) -> str:
    digest = hashlib.sha256()
    digest.update(TOPIC_ANALYSIS_PROMPT_VERSION.encode("utf-8"))
    for question in questions:
        digest.update(str(question.id).encode("ascii"))
        digest.update(b"\0")
        digest.update(question.content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _cache_key(scope: WorkflowScope, period_days: int) -> str:
    audience = (
        f"owner:{scope.actor_user_id}"
        if scope.is_card_owner
        else "company"
    )
    return (
        "admin:topic-analysis:v1:"
        f"{scope.tenant_id}:{scope.company_id}:{audience}:{period_days}"
    )


def _strip_json_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


__all__ = [
    "TOPIC_ANALYSIS_PROMPT_VERSION",
    "TOPIC_ANALYSIS_SYSTEM_PROMPT",
    "TopicAnalysisProvider",
    "TopicAnalysisService",
    "TopicGeneration",
    "TopicQuestion",
]
