"""Application-facing orchestration for safe, cited enterprise RAG answers."""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

from .errors import AIErrorCategory, AIProviderError, AIServiceError
from .policy import (
    EvidenceGate,
    InputSecurityPolicy,
    QuestionScope,
    classify_question_scope,
)
from .prompts import DEFAULT_PROMPT_VERSION, PromptRegistry, conversation_mode
from .protocols import (
    ChatProvider,
    EmbeddingProvider,
    FAQAnswerCache,
    FAQMatchRepository,
    RetrievalRepository,
    TextDeltaCallback,
)
from .schemas import (
    AIAnswer,
    AnswerPresentation,
    AnswerPresentationBlock,
    ChatCompletion,
    ChatMessage,
    Citation,
    ForbiddenTopicPolicy,
    ProviderCredentials,
    RAGRequest,
    Refusal,
    RefusalCode,
    RetrievalQuery,
    RetrievedEvidence,
    StructuredModelAnswer,
    TraceMetadata,
)

_COOPERATION_INTENT_PATTERN = re.compile(
    r"^(?:请问)?(?:我(?:们)?|本人|本公司|我们公司|企业)?"
    r"(?:想|希望|要|有意|考虑|寻求|准备|可以|能|能否|怎么|如何)?"
    r"(?:和|跟|与)?(?:你们|贵司|贵公司|拓浙(?:AI集团)?|公司)?"
    r"(?:进行|开展|谈|聊|对接|发起)?(?:一下)?(?:商务)?合作"
    r"(?:咨询|方式|流程|入口|机会)?(?:吗|么|可以吗|怎么弄|怎么联系)?$",
    re.IGNORECASE,
)
_CORE_BUSINESS_INTENT_PATTERN = re.compile(
    r"^(?:请问|请|介绍|说说|问)?(?:一下)?"
    r"(?:你们|贵司|贵公司|拓浙(?:AI集团)?|公司|企业)?(?:的)?"
    r"(?:三大|三项|核心|主要)?(?:业务|业务板块)"
    r"(?:是什么|有哪些|包括什么|分别是什么|介绍)?$",
    re.IGNORECASE,
)


def _canonical_faq_lookup_text(value: str) -> tuple[str, str | None]:
    """Map short action intents to one curated FAQ without changing the question."""

    compact = re.sub(r"\s+", "", value).rstrip("?？!！。.")
    if _COOPERATION_INTENT_PATTERN.fullmatch(compact):
        return "企业可以怎样与拓浙 AI 集团合作？", "cooperation"
    if _CORE_BUSINESS_INTENT_PATTERN.fullmatch(compact):
        return "拓浙 AI 集团有哪些业务板块？", "core_businesses"
    return value, None


@dataclass(frozen=True, slots=True)
class RAGOrchestratorConfig:
    prompt_version: str = DEFAULT_PROMPT_VERSION
    top_k: int = 6
    candidate_limit: int = 30
    trigram_threshold: float = 0.12
    rrf_k: int = 60
    vector_weight: float = 1.0
    lexical_weight: float = 1.0
    temperature: float = 0.1
    max_tokens: int = 1200
    citation_excerpt_chars: int = 320
    fallback_to_lexical_on_embedding_error: bool = True
    faq_fast_path_enabled: bool = False
    faq_similarity_threshold: float = 0.92
    faq_max_question_chars: int = 180

    def __post_init__(self) -> None:
        if self.top_k <= 0 or self.candidate_limit < self.top_k:
            raise ValueError("invalid retrieval limits")
        if not 0 <= self.trigram_threshold <= 1:
            raise ValueError("trigram_threshold must be between 0 and 1")
        if self.rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        if self.vector_weight < 0 or self.lexical_weight < 0:
            raise ValueError("retrieval weights must not be negative")
        if self.vector_weight == 0 and self.lexical_weight == 0:
            raise ValueError("at least one retrieval weight must be positive")
        if not 0 <= self.temperature <= 2 or self.max_tokens <= 0:
            raise ValueError("invalid chat generation settings")
        if self.citation_excerpt_chars <= 0:
            raise ValueError("citation_excerpt_chars must be positive")
        if not 0 <= self.faq_similarity_threshold <= 1:
            raise ValueError("faq_similarity_threshold must be between 0 and 1")
        if self.faq_max_question_chars <= 0:
            raise ValueError("faq_max_question_chars must be positive")


@dataclass(slots=True)
class _TraceState:
    trace_id: str
    query_fingerprint: str
    started_at: float
    prompt_version: str
    chat_provider: str
    chat_model: str
    embedding_provider: str | None
    embedding_model: str | None
    retrieval_mode: Literal["hybrid", "lexical", "skipped"] = "skipped"
    retrieval_count: int = 0
    policy_flags: tuple[str, ...] = ()
    retrieval_ms: int = 0
    model_ms: int = 0
    provider_request_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error_category: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def finish(self, citations: Sequence[Citation]) -> TraceMetadata:
        return TraceMetadata(
            trace_id=self.trace_id,
            query_fingerprint=self.query_fingerprint,
            prompt_version=self.prompt_version,
            chat_provider=self.chat_provider,
            chat_model=self.chat_model,
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            retrieval_mode=self.retrieval_mode,
            retrieval_count=self.retrieval_count,
            citation_count=len(citations),
            policy_flags=self.policy_flags,
            elapsed_ms=_elapsed_ms(self.started_at),
            retrieval_ms=self.retrieval_ms,
            model_ms=self.model_ms,
            provider_request_id=self.provider_request_id,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            error_category=self.error_category,
            extra=dict(self.extra),
        )


class RAGOrchestrator:
    """Coordinate safety, optional embeddings, retrieval, generation and gating.

    Provider credentials are method arguments and are not stored on this object.
    This makes the orchestrator safe to reuse across tenant requests.
    """

    def __init__(
        self,
        chat_provider: ChatProvider,
        retrieval_repository: RetrievalRepository,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        faq_repository: FAQMatchRepository | None = None,
        faq_cache: FAQAnswerCache | None = None,
        security_policy: InputSecurityPolicy | None = None,
        evidence_gate: EvidenceGate | None = None,
        prompt_registry: PromptRegistry | None = None,
        config: RAGOrchestratorConfig | None = None,
    ) -> None:
        self._chat_provider = chat_provider
        self._retrieval_repository = retrieval_repository
        self._embedding_provider = embedding_provider
        self._faq_repository = faq_repository
        self._faq_cache = faq_cache
        self._security_policy = security_policy or InputSecurityPolicy()
        self._evidence_gate = evidence_gate or EvidenceGate()
        self._prompt_registry = prompt_registry or PromptRegistry()
        self.config = config or RAGOrchestratorConfig()
        self._prompt_registry.get(self.config.prompt_version)

    async def answer(
        self,
        request: RAGRequest,
        *,
        chat_credentials: ProviderCredentials,
        embedding_credentials: ProviderCredentials | None = None,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> AIAnswer:
        started_at = time.perf_counter()
        trace_id = str(uuid.uuid4())
        policy = self._security_policy.evaluate(request.question)
        normalized = policy.normalized_text
        trace = _TraceState(
            trace_id=trace_id,
            query_fingerprint=_query_fingerprint(
                request.tenant_id,
                request.company_id,
                normalized,
            ),
            started_at=started_at,
            prompt_version=self.config.prompt_version,
            chat_provider=self._chat_provider.provider_name,
            chat_model=self._chat_provider.model_name,
            embedding_provider=(
                self._embedding_provider.provider_name if self._embedding_provider else None
            ),
            embedding_model=(
                self._embedding_provider.model_name if self._embedding_provider else None
            ),
            policy_flags=tuple(flag.value for flag in policy.flags),
        )
        if policy.blocked:
            trace.error_category = AIErrorCategory.SAFETY.value
            return _refused(policy.refusal, trace)

        forbidden = _match_forbidden_topic(normalized, request.forbidden_topics)
        if forbidden is not None:
            trace.policy_flags += ("forbidden_topic",)
            trace.error_category = AIErrorCategory.SAFETY.value
            trace.extra.update(
                {
                    "forbidden_rule_id": forbidden.rule_id,
                    "forbidden_rule_version": forbidden.version,
                    "forbidden_action": forbidden.action,
                    "needs_human_review": forbidden.action == "handoff",
                }
            )
            return _refused(_forbidden_refusal(forbidden), trace)

        direct_question_scope = classify_question_scope(normalized)
        question_scope = classify_question_scope(normalized, request.history)
        include_history_for_retrieval = _should_include_history_for_retrieval(
            normalized,
            direct_question_scope=direct_question_scope,
            history=request.history,
        )
        retrieval_text = _compose_retrieval_text(
            normalized,
            request.history,
            include_history=include_history_for_retrieval,
        )
        trace.extra["question_scope"] = question_scope.value
        trace.extra["question_scope_source"] = (
            "conversation" if direct_question_scope is QuestionScope.AMBIGUOUS else "direct"
        )
        if question_scope is QuestionScope.AMBIGUOUS:
            return _scope_clarification(trace)

        skip_retrieval = question_scope is QuestionScope.GENERAL
        faq_evidence = None
        if skip_retrieval:
            trace.extra["fast_faq_skipped"] = "general_question"
        elif not include_history_for_retrieval:
            faq_evidence = await self._find_fast_faq_evidence(
                request=request,
                normalized=normalized,
                trace=trace,
            )
        else:
            trace.extra["fast_faq_skipped"] = "contextual_follow_up"

        embedding: tuple[float, ...] | None = None
        if (
            not skip_retrieval
            and faq_evidence is None
            and self._embedding_provider is not None
            and embedding_credentials is not None
        ):
            embedding_started = time.perf_counter()
            try:
                batch = await self._embedding_provider.embed(
                    [retrieval_text],
                    credentials=embedding_credentials,
                    trace_id=trace_id,
                )
                if len(batch.embeddings) != 1:
                    raise ValueError("embedding provider returned the wrong batch size")
                embedding = batch.embeddings[0]
                trace.extra["embedding_request_id"] = batch.request_id
            except AIProviderError as exc:
                trace.extra["embedding_ms"] = _elapsed_ms(embedding_started)
                if not self.config.fallback_to_lexical_on_embedding_error:
                    trace.error_category = exc.category.value
                    return _refused(_provider_refusal(exc), trace)
                trace.extra["embedding_fallback_category"] = exc.category.value
                trace.extra["embedding_fallback_code"] = exc.code
            except (IndexError, ValueError):
                trace.extra["embedding_ms"] = _elapsed_ms(embedding_started)
                if not self.config.fallback_to_lexical_on_embedding_error:
                    trace.error_category = AIErrorCategory.INVALID_RESPONSE.value
                    return _refused(
                        Refusal(
                            code=RefusalCode.PROVIDER_ERROR,
                            reason="向量服务返回了无效结果。",
                            safe_alternative="请稍后重试。",
                        ),
                        trace,
                    )
                trace.extra["embedding_fallback_category"] = AIErrorCategory.INVALID_RESPONSE.value
                trace.extra["embedding_fallback_code"] = "invalid_embedding_batch"
            else:
                trace.extra["embedding_ms"] = _elapsed_ms(embedding_started)
        elif faq_evidence is not None:
            trace.extra["embedding_skipped"] = "faq_evidence_match"
        elif not skip_retrieval and self._embedding_provider is not None:
            trace.extra["embedding_skipped"] = "credentials_not_supplied"
        elif skip_retrieval:
            trace.extra["embedding_skipped"] = "general_question"

        if skip_retrieval:
            evidence = ()
            trace.retrieval_mode = "skipped"
            trace.extra["retrieval_skipped"] = "general_question"
        elif faq_evidence is not None:
            evidence = (faq_evidence,)
            trace.retrieval_mode = "lexical"
            trace.retrieval_ms = int(trace.extra.get("faq_lookup_ms", 0))
            trace.extra["interaction_kind"] = "faq_evidence_path"
        else:
            trace.retrieval_mode = "hybrid" if embedding is not None else "lexical"
            top_k = request.top_k if request.top_k is not None else self.config.top_k
            retrieval_started = time.perf_counter()
            try:
                evidence = tuple(
                    await self._retrieval_repository.search(
                        RetrievalQuery(
                            tenant_id=request.tenant_id,
                            company_id=request.company_id,
                            text=retrieval_text,
                            embedding=embedding,
                            top_k=top_k,
                            candidate_limit=max(top_k, self.config.candidate_limit),
                            trigram_threshold=self.config.trigram_threshold,
                            rrf_k=self.config.rrf_k,
                            vector_weight=self.config.vector_weight,
                            lexical_weight=self.config.lexical_weight,
                            card_id=request.card_id,
                        )
                    )
                )
            except AIServiceError as exc:
                trace.retrieval_ms = _elapsed_ms(retrieval_started)
                trace.error_category = exc.category.value
                return _refused(
                    Refusal(
                        code=RefusalCode.RETRIEVAL_ERROR,
                        reason="知识检索暂时不可用。",
                        retryable=exc.retryable,
                        safe_alternative="请稍后重试或联系企业工作人员。",
                    ),
                    trace,
                )
            trace.retrieval_ms = _elapsed_ms(retrieval_started)
        trace.retrieval_count = len(evidence)
        trace.extra["retrieved_evidence_ids"] = tuple(item.evidence_id for item in evidence)
        trace.extra["retrieved_version_ids"] = tuple(
            dict.fromkeys(item.version_id for item in evidence)
        )

        pre_gate = self._evidence_gate.before_generation(
            policy,
            evidence,
            question_scope=question_scope,
        )
        if not pre_gate.allowed:
            trace.error_category = AIErrorCategory.SAFETY.value
            trace.extra["needs_human_review"] = pre_gate.needs_human_review
            return _refused(
                _deduplicate_refusal(pre_gate.refusal, request.history),
                trace,
            )

        prompt = self._prompt_registry.get(self.config.prompt_version)
        prompt_evidence = (
            () if question_scope is QuestionScope.GENERAL else pre_gate.evidence
        )
        messages = prompt.render(
            question=normalized,
            evidence=prompt_evidence,
            policy=policy,
            history=request.history,
            general_answer_allowed=pre_gate.general_answer_allowed,
            question_scope=question_scope,
        )
        model_started = time.perf_counter()
        try:
            completion = await self._chat_provider.complete(
                messages,
                credentials=chat_credentials,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                trace_id=trace_id,
                on_text_delta=on_text_delta,
            )
        except AIProviderError as exc:
            trace.model_ms = _elapsed_ms(model_started)
            trace.error_category = exc.category.value
            trace.provider_request_id = exc.request_id
            return _refused(_provider_refusal(exc), trace)
        trace.model_ms = _elapsed_ms(model_started)
        _add_completion_trace(trace, completion)

        display_answer, answer_presentation = _model_answer_for_display(completion.output)
        if on_text_delta is None:
            display_answer, removed_lines = _deduplicate_continuation_answer(
                display_answer,
                request.history,
                mode=conversation_mode(normalized, request.history),
            )
            if removed_lines:
                answer_presentation = "deduplicated_continuation"
                trace.extra["answer_deduplicated"] = True
                trace.extra["deduplicated_line_count"] = removed_lines
        else:
            trace.extra["answer_streamed"] = True

        bridged_answer, bridge_action = _ensure_enterprise_bridge(
            display_answer,
            question=normalized,
            history=request.history,
            question_scope=question_scope,
        )
        if on_text_delta is None or bridge_action != "normalized":
            if (
                on_text_delta is not None
                and bridge_action == "appended"
                and bridged_answer.startswith(display_answer)
            ):
                await on_text_delta(bridged_answer[len(display_answer) :])
            display_answer = bridged_answer
        if bridge_action is not None:
            trace.extra["enterprise_bridge"] = bridge_action
        policy_output = completion.output.model_copy(update={"answer": display_answer})
        post_gate = self._evidence_gate.after_generation(
            policy,
            policy_output,
            pre_gate.evidence,
            question_scope=question_scope,
        )
        if not post_gate.allowed:
            trace.error_category = AIErrorCategory.SAFETY.value
            trace.extra["needs_human_review"] = post_gate.needs_human_review
            return _refused(post_gate.refusal, trace)

        citations = tuple(
            _citation_from_evidence(item, self.config.citation_excerpt_chars)
            for item in post_gate.evidence
        )
        trace.extra["needs_human_review"] = post_gate.needs_human_review
        trace.extra["answer_presentation"] = answer_presentation
        trace.extra["cited_content_hashes"] = tuple(
            citation.content_hash for citation in citations if citation.content_hash
        )
        return AIAnswer(
            answer=display_answer,
            citations=citations,
            refusal=None,
            trace=trace.finish(citations),
        )

    async def _find_fast_faq_evidence(
        self,
        *,
        request: RAGRequest,
        normalized: str,
        trace: _TraceState,
    ) -> RetrievedEvidence | None:
        if (
            self._faq_repository is None
            or len(normalized) > self.config.faq_max_question_chars
        ):
            return None

        fuzzy_enabled = self.config.faq_fast_path_enabled
        similarity_threshold = (
            self.config.faq_similarity_threshold if fuzzy_enabled else 1.0
        )
        lookup_text, normalized_intent = _canonical_faq_lookup_text(normalized)
        if normalized_intent is not None:
            trace.extra["faq_normalized_intent"] = normalized_intent

        query = RetrievalQuery(
            tenant_id=request.tenant_id,
            company_id=request.company_id,
            card_id=request.card_id,
            text=lookup_text,
            top_k=1,
            candidate_limit=max(1, self.config.candidate_limit),
            trigram_threshold=self.config.trigram_threshold,
            rrf_k=self.config.rrf_k,
            vector_weight=self.config.vector_weight,
            lexical_weight=self.config.lexical_weight,
        )
        lookup_started = time.perf_counter()
        evidence: RetrievedEvidence | None = None
        cache_hit = False
        if fuzzy_enabled and self._faq_cache is not None:
            evidence = await self._faq_cache.get(query)
            cache_hit = evidence is not None
        if evidence is None:
            try:
                evidence = await self._faq_repository.find_faq_match(
                    query,
                    similarity_threshold=similarity_threshold,
                )
            except AIServiceError as exc:
                # The fast path is an optimization. Fall through to the normal
                # hybrid pipeline when it is unavailable.
                trace.extra["faq_fast_path_error"] = exc.category.value
                trace.extra["faq_lookup_ms"] = _elapsed_ms(lookup_started)
                return None
            if evidence is not None and fuzzy_enabled and self._faq_cache is not None:
                await self._faq_cache.put(query, evidence)

        trace.extra["faq_cache_hit"] = cache_hit
        trace.extra["faq_match_mode"] = "fuzzy" if fuzzy_enabled else "exact_only"
        trace.extra["faq_lookup_ms"] = _elapsed_ms(lookup_started)
        if evidence is None:
            return None
        return evidence


_MARKDOWN_BLOCK_PATTERN = re.compile(
    r"(?m)^\s*(?:#{1,4}\s+|[-*+]\s+|\d+[.)]\s+|>\s+)"
)

AnswerPresentationMode = Literal[
    "model_markdown",
    "structured_blocks",
    "structured_emphasis",
    "metadata_markdown",
    "normalized_list",
    "source_text",
    "deduplicated_continuation",
]

_ENTERPRISE_TOPIC_PATTERN = re.compile(
    r"(?:这家(?:企业|公司)|企业(?:业务|产品|服务|案例|合作)|"
    r"公司(?:业务|产品|服务|案例|合作)|业务|产品|服务|案例|合作)"
)
_ENTERPRISE_BRIDGE_PATTERN = re.compile(
    r"(?:也可以|可以继续|欢迎|如果(?:你)?愿意|想继续时).{0,28}"
    r"(?:这家企业|这家公司|企业|公司|业务|产品|服务|案例|合作)"
)
_CASUAL_CHAT_PATTERN = re.compile(
    r"(?:你好|您好|在吗|早上好|下午好|晚上好|心情|有点累|累了|聊两句|"
    r"随便聊|闲聊|谢谢|辛苦了|晚安)"
)
_ENTERPRISE_GENERAL_BRIDGE = (
    "如果你愿意，也可以继续问我这家企业的业务、产品、案例或合作方式。"
)
_ENTERPRISE_CASUAL_BRIDGE = (
    "先轻松一下也好；想继续时，我也可以陪你了解这家企业的业务、产品或合作方式。"
)


def _ensure_enterprise_bridge(
    answer: str,
    *,
    question: str,
    history: Sequence[ChatMessage],
    question_scope: QuestionScope,
) -> tuple[str, Literal["appended", "normalized"] | None]:
    """Guarantee one light enterprise bridge in open chat without repetition."""

    if question_scope is not QuestionScope.GENERAL or not answer.strip():
        return answer, None

    bridge = (
        _ENTERPRISE_CASUAL_BRIDGE
        if _CASUAL_CHAT_PATTERN.search(question)
        else _ENTERPRISE_GENERAL_BRIDGE
    )
    paragraphs = re.split(r"\n\s*\n", answer.rstrip())
    for index, paragraph in enumerate(paragraphs):
        match = _ENTERPRISE_BRIDGE_PATTERN.search(paragraph)
        if match is None:
            continue
        useful_prefix = paragraph[: match.start()].rstrip(" ；;")
        paragraphs[index] = (
            f"{useful_prefix}\n\n{bridge}" if useful_prefix else bridge
        )
        return "\n\n".join(paragraphs), "normalized"

    if _ENTERPRISE_TOPIC_PATTERN.search(answer):
        return answer, None

    recent_assistant = (
        item.content
        for item in reversed(history[-6:])
        if item.role == "assistant"
    )
    if any(
        _ENTERPRISE_BRIDGE_PATTERN.search(message)
        or _ENTERPRISE_TOPIC_PATTERN.search(message)
        for message in recent_assistant
    ):
        return answer, None

    return f"{answer.rstrip()}\n\n{bridge}", "appended"


def _model_answer_for_display(
    output: StructuredModelAnswer,
) -> tuple[str, AnswerPresentationMode]:
    if output.presentation is not None:
        return _render_answer_presentation(output.presentation), "structured_blocks"
    emphasized = _render_plain_text_with_emphasis(
        output.answer,
        output.answer_emphasis,
    ) if output.answer_emphasis else output.answer
    if output.answer_emphasis:
        return emphasized.strip(), "structured_emphasis"
    return emphasized.strip(), "model_markdown"


def _deduplicate_continuation_answer(
    answer: str,
    history: Sequence[ChatMessage],
    *,
    mode: str,
) -> tuple[str, int]:
    if mode != "continuation" or not answer.strip():
        return answer, 0
    previous = next(
        (item.content for item in reversed(history) if item.role == "assistant"),
        "",
    )
    if not previous.strip():
        return answer, 0

    def normalized_line(value: str) -> str:
        return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()

    previous_lines = {
        normalized
        for line in previous.splitlines()
        if (normalized := normalized_line(line))
    }
    answer_lines = answer.splitlines()
    normalized_answer_lines = [normalized_line(line) for line in answer_lines]
    repeated_indexes = {
        index
        for index, normalized in enumerate(normalized_answer_lines)
        if len(normalized) >= 4 and normalized in previous_lines
    }
    repeated_chars = sum(
        len(normalized_answer_lines[index]) for index in repeated_indexes
    )
    total_chars = sum(len(value) for value in normalized_answer_lines)
    if repeated_chars < 40 or not total_chars or repeated_chars / total_chars < 0.5:
        return answer, 0

    kept: list[str] = []
    for index, line in enumerate(answer_lines):
        if index in repeated_indexes:
            continue
        if not line.strip() and (not kept or not kept[-1].strip()):
            continue
        kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    deduplicated = "\n".join(kept).strip()
    if not normalized_line(deduplicated):
        deduplicated = "与上一条结论一致，当前没有新增的可核验信息。"
    return deduplicated, len(repeated_indexes)


def _render_answer_presentation(presentation: AnswerPresentation) -> str:
    sections = [
        _render_plain_text_with_emphasis(
            presentation.lead,
            presentation.lead_emphasis,
        )
    ]
    for block in presentation.blocks:
        sections.append(_render_answer_block(block))
    return "\n\n".join(section for section in sections if section)


def _render_answer_block(block: AnswerPresentationBlock) -> str:
    title = _markdown_label(block.title) if block.title else None
    if block.type == "paragraph":
        text = _render_plain_text_with_emphasis(str(block.text), block.emphasis)
        return f"**{title}**\n\n{text}" if title else text
    if block.type == "note":
        prefix = f"**{title}：** " if title else ""
        text = _render_plain_text_with_emphasis(str(block.text), block.emphasis)
        return f"> {prefix}{text}"

    if block.type == "facts":
        rows = [
            "| 项目 | 信息 |",
            "| --- | --- |",
            *(
                f"| **{_markdown_table_cell(str(item.label))}** | "
                f"{_markdown_table_cell(str(item.text))} |"
                for item in block.items
            ),
        ]
        return f"**{title}**\n\n" + "\n".join(rows)

    marker = "{index}." if block.type == "steps" else "-"
    items = []
    for index, item in enumerate(block.items, start=1):
        item_text = _markdown_copy(item.text or "")
        if item.label and item.text:
            item_text = f"**{_markdown_label(item.label)}：** {item_text}"
        elif item.label:
            item_text = f"**{_markdown_label(item.label)}**"
        elif item.text:
            item_text = _emphasize_inline_item_label(item.text)
        items.append(f"{marker.format(index=index)} {item_text}")
    return f"**{title}**\n\n" + "\n".join(items)


def _emphasize_inline_item_label(value: str) -> str:
    for separator in ("：", ":"):
        if separator not in value:
            continue
        label, detail = (part.strip() for part in value.split(separator, 1))
        if (
            label
            and detail
            and len(label) <= 40
            and not re.search(r"[，。；!?！？]", label)
        ):
            return f"**{_markdown_label(label)}：** {_markdown_copy(detail)}"
    return _markdown_copy(value)


def _render_plain_text_with_emphasis(value: str, emphasis: Sequence[str]) -> str:
    terms = sorted(dict.fromkeys(emphasis), key=len, reverse=True)
    if not terms:
        return _markdown_copy(value)

    pattern = re.compile("|".join(re.escape(term) for term in terms))
    rendered: list[str] = []
    cursor = 0
    for match in pattern.finditer(value):
        rendered.append(_markdown_copy(value[cursor : match.start()]))
        rendered.append(f"**{_markdown_copy(match.group(0))}**")
        cursor = match.end()
    rendered.append(_markdown_copy(value[cursor:]))
    return "".join(rendered)


def _markdown_copy(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    for token in ("*", "_", "`", "[", "]", "<", ">"):
        escaped = escaped.replace(token, f"\\{token}")
    return escaped


def _markdown_label(value: str) -> str:
    return _markdown_copy(value)


def _markdown_table_cell(value: str) -> str:
    return _markdown_copy(value).replace("|", "\\|")


def _faq_answer_for_display(
    evidence: RetrievedEvidence,
) -> tuple[str, AnswerPresentationMode]:
    configured = evidence.metadata.get("answer_markdown")
    if isinstance(configured, str) and configured.strip():
        return configured.strip(), "metadata_markdown"
    formatted = _format_answer_for_display(evidence.text)
    presentation = "normalized_list" if formatted != evidence.text.strip() else "source_text"
    return formatted, presentation


def _format_answer_for_display(value: str) -> str:
    """Add compact Markdown only when a dense answer contains an obvious list.

    This formatter never invents labels or rewrites claims. It only moves
    already-delimited list items onto separate lines so model variance cannot
    collapse a multi-point mobile answer back into one paragraph.
    """

    text = value.strip()
    if len(text) < 36 or "\n" in text or _MARKDOWN_BLOCK_PATTERN.search(text):
        return text

    for colon in ("：", ":"):
        if colon not in text:
            continue
        lead, remainder = text.split(colon, 1)
        if not lead.strip() or len(lead.strip()) > 48:
            continue
        remainder = remainder.strip().rstrip("。.!！?？")
        for separator in ("；", ";", "、"):
            parts = [part.strip().rstrip("。.;；") for part in remainder.split(separator)]
            if not 3 <= len(parts) <= 6:
                continue
            if any(not part or len(part) > 64 for part in parts):
                continue
            bullets = "\n".join(f"- {part}" for part in parts)
            return f"**结论：** {lead.strip()}{colon}\n\n{bullets}"

    action_match = re.fullmatch(
        r"(?P<intro>[^。]{1,32}?)(?:可)?通过(?P<ways>[^。]+?)"
        r"等方式(?P<tail>[^。]*)。(?P<rest>.+)",
        text,
    )
    if action_match is not None:
        ways = _split_compact_items(action_match.group("ways"))
        if 3 <= len(ways) <= 6:
            label = "合作方式" if "合作" in text else "可选方式"
            sections = [f"**{label}：**\n\n" + "\n".join(f"- {item}" for item in ways)]
            rest = action_match.group("rest").strip()
            process_match = re.fullmatch(
                r"(?P<prefix>[^，；。]{0,24}?流程[^，；。]*包括)"
                r"(?P<steps>.+?)(?:，|；)(?P<note>具体.+)",
                rest,
            )
            if process_match is not None:
                steps = _split_compact_items(process_match.group("steps"))
                if 3 <= len(steps) <= 8:
                    process_label = (
                        "合作流程" if "合作流程" in process_match.group("prefix") else "流程"
                    )
                    sections.append(f"**{process_label}：** " + " → ".join(steps))
                    sections.append(f"> {process_match.group('note').strip()}")
                    return "\n\n".join(sections)
            sections.append(rest)
            return "\n\n".join(sections)

    return text


def _split_compact_items(value: str) -> list[str]:
    return [
        item.strip().rstrip("。.;；")
        for item in re.split(r"[、，]|\s*(?:或|以及)\s*", value)
        if item.strip()
    ]


def _add_completion_trace(trace: _TraceState, completion: ChatCompletion) -> None:
    trace.provider_request_id = completion.request_id
    trace.input_tokens = completion.usage.input_tokens
    trace.output_tokens = completion.usage.output_tokens
    trace.extra["response_model"] = completion.model


def _provider_refusal(error: AIProviderError) -> Refusal:
    reason = "AI 服务暂时不可用。" if error.retryable else "AI 服务请求未能完成。"
    return Refusal(
        code=RefusalCode.PROVIDER_ERROR,
        reason=reason,
        retryable=error.retryable,
        safe_alternative="请稍后重试或联系企业工作人员。",
    )


def _refused(refusal: Refusal | None, trace: _TraceState) -> AIAnswer:
    safe_refusal = refusal or Refusal(
        code=RefusalCode.INPUT_INVALID,
        reason="请求无法处理。",
    )
    return AIAnswer(
        answer="",
        citations=(),
        refusal=safe_refusal,
        trace=trace.finish(()),
    )


def _deduplicate_refusal(
    refusal: Refusal | None,
    history: Sequence[ChatMessage],
) -> Refusal | None:
    if refusal is None:
        return None
    previous = next(
        (item.content for item in reversed(history) if item.role == "assistant"),
        "",
    )
    current = " ".join(
        part for part in (refusal.reason, refusal.safe_alternative) if part
    )
    def normalize(value: str) -> str:
        return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()

    if not previous or normalize(previous) != normalize(current):
        return refusal
    return Refusal(
        code=refusal.code,
        reason="与上一条结论一致，当前没有新增的可核验信息。",
        retryable=refusal.retryable,
    )


def _scope_clarification(trace: _TraceState) -> AIAnswer:
    trace.extra.update(
        {
            "interaction_kind": "scope_clarification",
            "answer_presentation": "deterministic_clarification",
        }
    )
    return AIAnswer(
        answer="你是想了解当前企业的相关情况，还是询问通用知识？请补充一下具体对象。",
        citations=(),
        refusal=None,
        trace=trace.finish(()),
    )


def _match_forbidden_topic(
    text: str,
    rules: Sequence[ForbiddenTopicPolicy],
) -> ForbiddenTopicPolicy | None:
    normalized = " ".join(text.casefold().split())
    best: tuple[int, int, ForbiddenTopicPolicy] | None = None
    for rule in rules:
        matched_lengths = [
            len(candidate)
            for term in (rule.topic, *rule.match_terms)
            if (candidate := " ".join(term.casefold().split()))
            and _rule_term_matches(normalized, candidate)
        ]
        if not matched_lengths:
            continue
        candidate_rule = (max(matched_lengths), rule.version, rule)
        if best is None or candidate_rule[:2] > best[:2]:
            best = candidate_rule
    return best[2] if best else None


def _rule_term_matches(text: str, term: str) -> bool:
    simple_ascii = term.isascii() and all(
        character.isalnum() or character in {"-", "_", " "} for character in term
    )
    if simple_ascii:
        return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None
    return term in text


def _forbidden_refusal(rule: ForbiddenTopicPolicy) -> Refusal:
    if rule.action == "safe_template":
        return Refusal(
            code=RefusalCode.FORBIDDEN_TOPIC,
            reason=rule.safe_response or "该话题暂不在企业授权答复范围内。",
        )
    if rule.action == "handoff":
        return Refusal(
            code=RefusalCode.FORBIDDEN_TOPIC,
            reason="该问题需要由企业工作人员进一步确认。",
            safe_alternative=rule.safe_response or "您可以留下联系方式，我们会安排人工跟进。",
        )
    return Refusal(
        code=RefusalCode.FORBIDDEN_TOPIC,
        reason="该话题不在企业授权答复范围内。",
        safe_alternative=rule.safe_response or "可以继续咨询已发布的企业、产品或服务信息。",
    )


def _citation_from_evidence(evidence: RetrievedEvidence, max_chars: int) -> Citation:
    excerpt = " ".join(evidence.text.split())
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1].rstrip() + "…"
    return Citation(
        evidence_id=evidence.evidence_id,
        document_id=evidence.document_id,
        version_id=evidence.version_id,
        ordinal=evidence.ordinal,
        title=evidence.title,
        excerpt=excerpt,
        source_url=evidence.source_url,
        content_hash=evidence.content_hash,
        score=evidence.score,
    )


def _query_fingerprint(tenant_id: str, company_id: str, normalized: str) -> str:
    material = f"{tenant_id}\x00{company_id}\x00{normalized}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _elapsed_ms(started_at: float) -> int:
    return max(0, round((time.perf_counter() - started_at) * 1000))


_CONTEXTUAL_RETRIEVAL_PATTERN = re.compile(
    r"^(?:(?:它|其)(?:的|们的)?|这个(?:产品|服务|项目|方案|案例|方向|板块)|"
    r"那个(?:产品|服务|项目|方案|案例|方向|板块)|这些|那些|上述|前面|上面|刚才|"
    r"其中|第[一二三四五六七八九十\d]+个)"
)


def _should_include_history_for_retrieval(
    normalized: str,
    *,
    direct_question_scope: QuestionScope,
    history: Sequence[ChatMessage],
) -> bool:
    if not history:
        return False
    if direct_question_scope is QuestionScope.AMBIGUOUS:
        return True
    return bool(_CONTEXTUAL_RETRIEVAL_PATTERN.search(normalized))


def _compose_retrieval_text(
    normalized: str,
    history: Sequence[ChatMessage],
    *,
    include_history: bool,
) -> str:
    if not include_history:
        return normalized
    recent_turns = [
        re.sub(r"\s+", " ", str(item.content)).strip()[:400]
        for item in history
        if item.role in {"user", "assistant"} and item.content.strip()
    ][-4:]
    if not recent_turns:
        return normalized
    return "\n".join([*recent_turns, normalized])
