from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from app.ai import ProviderCredentials, RAGRequest
from app.api.dependencies import get_idempotency_key, get_visitor_principal
from app.api.errors import ApiError
from app.api.schemas import (
    ConsentEnvelope,
    ConsentRequest,
    ConversationEnvelope,
    CreateConversationRequest,
    CreateMessageRequest,
    CreateVisitRequest,
    MessageCompleted,
    MessageDelta,
    MessageError,
    MessageStarted,
    PublicCardEnvelope,
    VisitEnvelope,
)
from app.api.sse import encode_sse
from app.core.metrics import MetricsRegistry
from app.core.rate_limit import RateLimitBackendUnavailable, RedisRateLimiter
from app.core.request_context import request_id_ctx
from app.core.request_security import request_ip_hash, security_subject_hash
from app.core.tokens import VisitorPrincipal
from app.services.ai_runtime import ResolvedRAGRuntime, resolve_rag_runtime
from app.services.platform_llm_profiles import LLMRuntimeUnavailable, is_chat_available
from app.services.public_store import (
    PreparedMessage,
    PublicStore,
    StoredAnswer,
    citations_to_schema,
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Public Conversation"])
VisitorDependency = Annotated[VisitorPrincipal, Depends(get_visitor_principal)]
IdempotencyDependency = Annotated[str, Depends(get_idempotency_key)]


def _store(request: Request) -> PublicStore:
    return PublicStore(request.app.state.session_factory, request.app.state.settings)


def _visitor_channel(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "").casefold()
    if "wxwork" in user_agent:
        return "wecom"
    if "micromessenger" in user_agent:
        return "wechat"
    return "web"


@router.get(
    "/public/cards/{slug}",
    response_model=PublicCardEnvelope,
    operation_id="getPublicCard",
)
async def get_public_card(slug: str, request: Request) -> PublicCardEnvelope:
    card = await _store(request).get_public_card(slug=slug)
    llm_available = await is_chat_available(
        request.app.state.session_factory,
        request.app.state.settings,
    )
    card = card.model_copy(
        update={
            "ai_assistant": card.ai_assistant.model_copy(
                update={"available": card.ai_assistant.available and llm_available}
            )
        }
    )
    return PublicCardEnvelope(data=card)


def _runtime_semaphore(request: Request, runtime: ResolvedRAGRuntime) -> asyncio.Semaphore:
    """Return a bounded semaphore for the exact profile/version runtime."""

    cache: dict[tuple[str, int], asyncio.Semaphore] = getattr(
        request.app.state, "ai_runtime_semaphores", {}
    )
    request.app.state.ai_runtime_semaphores = cache
    profile_key = str(runtime.config.profile_id or "environment")
    key = (profile_key, runtime.config.version)
    semaphore = cache.get(key)
    if semaphore is None:
        semaphore = asyncio.Semaphore(runtime.settings.llm_max_concurrency)
        cache[key] = semaphore
        # Profiles are versioned; retain only a small number of old semaphores
        # while in-flight requests finish.
        while len(cache) > 16:
            cache.pop(next(iter(cache)))
    return semaphore


@router.post(
    "/public/cards/{slug}/visits",
    response_model=VisitEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createVisit",
)
async def create_visit(
    slug: str,
    body: CreateVisitRequest,
    request: Request,
    idempotency_key: IdempotencyDependency,
) -> VisitEnvelope:
    settings = request.app.state.settings
    ip_hash = request_ip_hash(request, settings)
    await _enforce_public_rate_limit(
        request=request,
        bucket="public-visit-ip-card",
        subject=security_subject_hash(
            settings,
            "public-visit-ip-card",
            ip_hash,
            slug.strip().casefold(),
        ),
        limit=settings.public_visit_ip_card_rate_limit_per_minute,
    )
    visit = await _store(request).create_visit(
        slug=slug,
        request=body,
        idempotency_key=idempotency_key,
        visitor_channel=_visitor_channel(request),
    )
    return VisitEnvelope(data=visit)


@router.post(
    "/public/cards/{slug}/consents",
    response_model=ConsentEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="recordConsent",
)
async def record_consent(
    slug: str,
    body: ConsentRequest,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> ConsentEnvelope:
    consent = await _store(request).record_consent(
        slug=slug,
        principal=principal,
        request=body,
        idempotency_key=idempotency_key,
    )
    return ConsentEnvelope(data=consent)


@router.post(
    "/public/cards/{slug}/conversations",
    response_model=ConversationEnvelope,
    status_code=status.HTTP_201_CREATED,
    operation_id="createConversation",
)
async def create_conversation(
    slug: str,
    body: CreateConversationRequest,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> ConversationEnvelope:
    conversation = await _store(request).create_conversation(
        slug=slug,
        principal=principal,
        request=body,
        idempotency_key=idempotency_key,
    )
    return ConversationEnvelope(data=conversation)


@router.post(
    "/public/conversations/{conversation_id}/messages:stream",
    operation_id="streamConversationMessage",
)
async def stream_message(
    conversation_id: uuid.UUID,
    body: CreateMessageRequest,
    request: Request,
    principal: VisitorDependency,
    idempotency_key: IdempotencyDependency,
) -> Response:
    settings = request.app.state.settings
    ip_hash = request_ip_hash(request, settings)
    await _enforce_public_rate_limit(
        request=request,
        bucket="public-chat-ip-card",
        subject=security_subject_hash(
            settings,
            "public-chat-ip-card",
            ip_hash,
            principal.card_id,
        ),
        limit=settings.public_chat_ip_card_rate_limit_per_minute,
    )
    await _enforce_public_rate_limit(
        request=request,
        bucket="public-chat-session",
        subject=principal.rate_limit_subject,
        limit=settings.public_chat_rate_limit_per_minute,
    )

    store = _store(request)
    prepared = await store.prepare_message(
        conversation_id=conversation_id,
        principal=principal,
        content=body.content,
        idempotency_key=idempotency_key,
    )
    stored = await store.load_stored_answer(prepared=prepared, principal=principal)
    task: asyncio.Task[StoredAnswer] | None = None
    delta_queue: asyncio.Queue[str | None] | None = None
    if stored is None:
        delta_queue = asyncio.Queue()
        task = asyncio.create_task(
            _generate_and_persist(
                request=request,
                store=store,
                principal=principal,
                prepared=prepared,
                delta_queue=delta_queue,
            ),
            name=f"ai-answer:{prepared.assistant_message_id}",
        )
        request.app.state.ai_tasks.add(task)
        task.add_done_callback(lambda completed: _finish_background_task(request, completed))

    stream = _answer_events(
        message_id=prepared.assistant_message_id,
        request_id=request_id_ctx.get(),
        stored=stored,
        task=task,
        delta_queue=delta_queue,
        metrics=getattr(request.app.state, "metrics", None),
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id_ctx.get(),
        },
    )


async def _enforce_public_rate_limit(
    *,
    request: Request,
    bucket: str,
    subject: str,
    limit: int,
) -> None:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        if request.app.state.settings.app_env == "test":
            return
        raise ApiError(503, "RATE_LIMIT_UNAVAILABLE", "访问保护服务正在恢复，请稍后重试")
    try:
        decision = await RedisRateLimiter(redis).check(
            bucket=bucket,
            subject=subject,
            limit=limit,
            window_seconds=60,
        )
    except RateLimitBackendUnavailable as exc:
        raise ApiError(
            503,
            "RATE_LIMIT_UNAVAILABLE",
            "访问保护服务正在恢复，请稍后重试",
        ) from exc
    if not decision.allowed:
        raise ApiError(
            429,
            "RATE_LIMITED",
            "请求过于频繁，请稍后重试",
            headers={"Retry-After": str(decision.retry_after_seconds)},
        )


async def _generate_and_persist(
    *,
    request: Request,
    store: PublicStore,
    principal: VisitorPrincipal,
    prepared: PreparedMessage,
    delta_queue: asyncio.Queue[str | None] | None = None,
) -> StoredAnswer:
    # This function is deliberately independent from the response stream so it
    # can finish and persist after a client disconnect.
    base_settings = request.app.state.settings
    metrics: MetricsRegistry | None = getattr(request.app.state, "metrics", None)
    try:
        runtime = await resolve_rag_runtime(
            settings=base_settings,
            http_client=request.app.state.http_client,
            session_factory=request.app.state.session_factory,
            redis=getattr(request.app.state, "redis", None),
        )
    except LLMRuntimeUnavailable as exc:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=base_settings.llm_provider,
                model=base_settings.llm_model,
                category=exc.code,
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code=f"LLM_{exc.code.upper()}",
        )
        if delta_queue is not None:
            delta_queue.put_nowait(None)
        raise ApiError(503, "MODEL_UNAVAILABLE", "AI 服务尚未配置") from exc

    settings = runtime.settings
    api_key = runtime.config.api_key
    semaphore = _runtime_semaphore(request, runtime)
    acquired = False
    try:
        await store.ensure_ai_configuration(
            principal=principal,
            runtime_settings=settings,
            profile_id=runtime.config.profile_id,
        )
        await store.assert_model_budget(principal=principal)
        async with asyncio.timeout(settings.llm_queue_timeout_seconds):
            await semaphore.acquire()
            acquired = True

        embedding_credentials = None
        if settings.embedding_provider and settings.embedding_api_key:
            embedding_credentials = ProviderCredentials(
                settings.embedding_api_key.get_secret_value()
            )
        # These reads use independent short-lived sessions. Fetch them together
        # so database round trips do not add up before retrieval and the upstream
        # model request start.
        history, forbidden_topics, company_context, prior_off_topic_question_count = (
            await asyncio.gather(
                store.load_conversation_history(
                    prepared=prepared,
                    principal=principal,
                ),
                store.load_forbidden_topic_rules(principal=principal),
                store.load_company_chat_context(principal=principal),
                store.load_off_topic_question_count(
                    prepared=prepared,
                    principal=principal,
                ),
            )
        )
        orchestrator = getattr(request.app.state, "rag_orchestrator", None)
        if orchestrator is None:
            orchestrator = runtime.orchestrator

        async def emit_text_delta(text: str) -> None:
            if delta_queue is not None and text:
                delta_queue.put_nowait(text)

        result = await orchestrator.answer(
            RAGRequest(
                tenant_id=str(principal.tenant_id),
                company_id=str(principal.company_id),
                card_id=str(principal.card_id),
                question=prepared.question,
                company_name=company_context.company_name,
                history=history,
                forbidden_topics=forbidden_topics,
                prior_off_topic_question_count=prior_off_topic_question_count,
                off_topic_policy=company_context.off_topic_policy,
            ),
            chat_credentials=ProviderCredentials(api_key.get_secret_value()),
            embedding_credentials=embedding_credentials,
            on_text_delta=emit_text_delta if delta_queue is not None else None,
        )
        stored_answer = await store.persist_ai_answer(
            prepared=prepared,
            principal=principal,
            result=result,
        )
        if metrics is not None:
            trace = result.trace
            estimated_cost = (
                trace.input_tokens * settings.llm_input_price_cny_per_million
                + trace.output_tokens * settings.llm_output_price_cny_per_million
            ) / 1_000_000
            metrics.observe_ai_result(
                provider=trace.chat_provider,
                model=trace.chat_model,
                outcome="refusal" if result.refused else "success",
                retrieval_mode=trace.retrieval_mode,
                duration_seconds=trace.elapsed_ms / 1_000,
                model_seconds=trace.model_ms / 1_000,
                input_tokens=trace.input_tokens,
                output_tokens=trace.output_tokens,
                estimated_cost_cny=estimated_cost,
                retrieval_count=trace.retrieval_count,
                citation_count=trace.citation_count,
                refusal_code=result.refusal.code.value if result.refusal else None,
                query_complexity=str(trace.extra.get("query_complexity", "not_applicable")),
                confidence_band=str(trace.extra.get("confidence_band", "not_applicable")),
                subquery_count=int(trace.extra.get("subquery_count", 0)),
                coverage_ratio=float(trace.extra.get("retrieval_coverage_ratio", 1.0)),
            )
        return stored_answer
    except TimeoutError as exc:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=settings.llm_provider,
                model=settings.llm_model,
                category="queue_timeout",
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code="MODEL_QUEUE_FULL",
        )
        raise ApiError(429, "MODEL_BUSY", "AI 服务繁忙，请稍后重试") from exc
    except ApiError as exc:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=settings.llm_provider,
                model=settings.llm_model,
                category=exc.code,
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code=exc.code,
        )
        raise
    except Exception as exc:
        if metrics is not None:
            metrics.observe_ai_error(
                provider=settings.llm_provider,
                model=settings.llm_model,
                category="unexpected",
            )
        await store.persist_ai_failure(
            prepared=prepared,
            principal=principal,
            error_code=type(exc).__name__,
        )
        raise ApiError(503, "MODEL_UNAVAILABLE", "AI 服务暂不可用，请稍后重试") from exc
    finally:
        if acquired:
            semaphore.release()
        if delta_queue is not None:
            delta_queue.put_nowait(None)


async def _answer_events(
    *,
    message_id: uuid.UUID,
    request_id: str,
    stored: StoredAnswer | None,
    task: asyncio.Task[StoredAnswer] | None,
    delta_queue: asyncio.Queue[str | None] | None = None,
    metrics: MetricsRegistry | None = None,
) -> AsyncIterator[bytes]:
    stream_started = time.perf_counter()
    answer_source = "cache" if stored is not None else "generated"
    yield encode_sse(
        "message.started",
        MessageStarted(message_id=message_id, request_id=request_id).model_dump(mode="json"),
    )
    answer = stored
    streamed_parts: list[str] = []
    if answer is None and task is not None:
        try:
            if delta_queue is not None:
                while True:
                    try:
                        delta = await asyncio.wait_for(delta_queue.get(), timeout=10)
                    except TimeoutError:
                        yield b": keep-alive\n\n"
                        continue
                    if delta is None:
                        break
                    streamed_parts.append(delta)
                    if len(streamed_parts) == 1 and metrics is not None:
                        metrics.observe_first_token(
                            source=answer_source,
                            duration_seconds=time.perf_counter() - stream_started,
                        )
                    yield encode_sse(
                        "message.delta",
                        MessageDelta(text=delta).model_dump(mode="json"),
                    )
            else:
                while not task.done():
                    done, _ = await asyncio.wait({task}, timeout=10)
                    if not done:
                        yield b": keep-alive\n\n"
            answer = await asyncio.shield(task)
        except ApiError as exc:
            yield encode_sse(
                "message.error",
                MessageError(
                    code=exc.code,
                    retryable=exc.status_code in {429, 503},
                    request_id=request_id,
                ).model_dump(mode="json"),
            )
            return
        except Exception:
            yield encode_sse(
                "message.error",
                MessageError(
                    code="MODEL_UNAVAILABLE",
                    retryable=True,
                    request_id=request_id,
                ).model_dump(mode="json"),
            )
            return
    if answer is None:
        yield encode_sse(
            "message.error",
            MessageError(
                code="MESSAGE_NOT_READY",
                retryable=True,
                request_id=request_id,
            ).model_dump(mode="json"),
        )
        return

    streamed_text = "".join(streamed_parts)
    if not streamed_text:
        remaining_text = answer.text
    elif answer.text.startswith(streamed_text):
        remaining_text = answer.text[len(streamed_text) :]
    else:
        remaining_text = ""
        logger.warning(
            "streamed_ai_answer_mismatch",
            message_id=str(answer.message_id),
            streamed_chars=len(streamed_text),
            stored_chars=len(answer.text),
        )

    first_content = not streamed_parts
    for chunk in _text_chunks(remaining_text) if remaining_text else ():
        if first_content and metrics is not None:
            metrics.observe_first_token(
                source=answer_source,
                duration_seconds=time.perf_counter() - stream_started,
            )
            first_content = False
        yield encode_sse(
            "message.delta",
            MessageDelta(text=chunk).model_dump(mode="json"),
        )
    for citation in citations_to_schema(answer.citations):
        yield encode_sse("message.citation", citation.model_dump(mode="json"))
    yield encode_sse(
        "message.completed",
        MessageCompleted(
            message_id=answer.message_id,
            finish_reason=answer.finish_reason,
            lead_prompt=answer.lead_prompt,
        ).model_dump(mode="json"),
    )


def _text_chunks(value: str, size: int = 48) -> tuple[str, ...]:
    if not value:
        return ("",)
    return tuple(value[index : index + size] for index in range(0, len(value), size))


def _finish_background_task(request: Request, task: asyncio.Task[StoredAnswer]) -> None:
    request.app.state.ai_tasks.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.warning(
            "background_ai_answer_failed",
            error_type=type(error).__name__,
            task_name=task.get_name(),
        )
