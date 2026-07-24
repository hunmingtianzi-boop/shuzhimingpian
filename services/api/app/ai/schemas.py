"""Public schemas and immutable value objects for AI/RAG orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StructuredOutputMode(StrEnum):
    """OpenAI-compatible structured-output dialect."""

    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"
    NONE = "none"


class RefusalCode(StrEnum):
    INPUT_INVALID = "input_invalid"
    PROMPT_INJECTION = "prompt_injection"
    SENSITIVE_DATA_REQUEST = "sensitive_data_request"
    HIGH_RISK_UNSUPPORTED = "high_risk_unsupported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNVERIFIED_PRICING = "unverified_pricing"
    UNGROUNDED_OUTPUT = "ungrounded_output"
    MODEL_REFUSAL = "model_refusal"
    PROVIDER_ERROR = "provider_error"
    RETRIEVAL_ERROR = "retrieval_error"
    FORBIDDEN_TOPIC = "forbidden_topic"


@dataclass(frozen=True, slots=True)
class ProviderCredentials:
    """A per-call credential whose repr and comparisons never reveal the key."""

    api_key: str = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.api_key or not self.api_key.strip():
            raise ValueError("api_key must not be empty")

    def authorization_value(self) -> str:
        """Build the Authorization value at the final transport boundary."""

        return f"Bearer {self.api_key}"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class AnswerPresentationItem(BaseModel):
    """One scannable item inside a model-authored presentation block."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str | None = Field(default=None, max_length=180)
    label: str | None = Field(default=None, max_length=40)

    @field_validator("text", "label")
    @classmethod
    def keep_item_inline(cls, value: str | None) -> str | None:
        if value is not None and "\n" in value:
            raise ValueError("presentation item text must stay on one line")
        return value

    @model_validator(mode="after")
    def require_item_content(self) -> "AnswerPresentationItem":
        if not self.label and not self.text:
            raise ValueError("presentation items require a label or text")
        return self


class AnswerPresentationBlock(BaseModel):
    """A single semantic block that the API can serialize consistently."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["paragraph", "bullets", "steps", "facts", "note"]
    title: str | None = Field(default=None, max_length=40)
    text: str | None = Field(default=None, max_length=600)
    emphasis: list[str] = Field(default_factory=list, max_length=3)
    items: list[AnswerPresentationItem] = Field(default_factory=list, max_length=5)

    @field_validator("title", "text")
    @classmethod
    def keep_block_copy_inline(cls, value: str | None) -> str | None:
        if value is not None and "\n" in value:
            raise ValueError("presentation block copy must stay on one line")
        return value

    @model_validator(mode="after")
    def validate_block_shape(self) -> "AnswerPresentationBlock":
        self.emphasis = _matching_emphasis_terms(self.emphasis, self.text or "")
        if self.type in {"paragraph", "note"}:
            if not self.text or self.items:
                raise ValueError(f"{self.type} blocks require text and no items")
            return self

        if not self.title or self.text or not 2 <= len(self.items) <= 5:
            raise ValueError(
                f"{self.type} blocks require a title, two to five items, and no text"
            )
        if self.type == "steps" and any(not item.text for item in self.items):
            raise ValueError("steps blocks require text for every item")
        if self.type == "facts" and any(
            not item.label or not item.text for item in self.items
        ):
            raise ValueError("facts blocks require a label and text for every item")
        return self


class AnswerPresentation(BaseModel):
    """Bounded mobile-first information hierarchy authored by the model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    lead: str = Field(min_length=1, max_length=300)
    lead_emphasis: list[str] = Field(default_factory=list, max_length=3)
    blocks: list[AnswerPresentationBlock] = Field(default_factory=list, max_length=3)

    @field_validator("lead")
    @classmethod
    def keep_lead_inline(cls, value: str) -> str:
        if "\n" in value:
            raise ValueError("presentation lead must stay on one line")
        return value

    @model_validator(mode="after")
    def keep_only_emphasis_from_lead(self) -> "AnswerPresentation":
        self.lead_emphasis = _matching_emphasis_terms(self.lead_emphasis, self.lead)
        return self


class StructuredModelAnswer(BaseModel):
    """Strict payload generated by the chat model before policy validation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    answer: str = ""
    answer_emphasis: list[str] = Field(default_factory=list, max_length=3)
    presentation: AnswerPresentation | None = None
    cited_evidence_ids: list[str] = Field(default_factory=list)
    refusal_reason: str | None = None
    needs_human_review: bool = False

    @model_validator(mode="after")
    def validate_answer_or_refusal(self) -> "StructuredModelAnswer":
        has_content = bool(self.answer or self.presentation)
        if not has_content and not self.refusal_reason:
            raise ValueError("answer, presentation, or refusal_reason is required")
        if has_content and self.refusal_reason:
            raise ValueError("answer content and refusal_reason are mutually exclusive")
        if self.answer and self.presentation:
            raise ValueError("answer and presentation are mutually exclusive")
        self.answer_emphasis = _matching_emphasis_terms(
            self.answer_emphasis,
            self.answer,
        )
        self.cited_evidence_ids = list(dict.fromkeys(self.cited_evidence_ids))
        return self


def _matching_emphasis_terms(values: list[str], source: str) -> list[str]:
    """Keep a small, exact set of safe inline terms from model-authored copy."""

    matched: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if (
            2 <= len(value) <= 24
            and "\n" not in value
            and not any(separator in value for separator in ("、", "，", ",", "；", ";"))
            and value in source
            and value not in matched
        ):
            matched.append(value)
    return matched


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class ChatCompletion:
    output: StructuredModelAnswer
    provider: str
    model: str
    request_id: str | None = None
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    embeddings: tuple[tuple[float, ...], ...]
    provider: str
    model: str
    request_id: str | None = None
    usage: TokenUsage = TokenUsage()


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    """A published, tenant-scoped knowledge chunk returned by retrieval."""

    evidence_id: str
    document_id: str
    version_id: str
    ordinal: int
    title: str
    text: str
    score: float
    vector_score: float | None = None
    lexical_score: float | None = None
    content_hash: str | None = None
    embedding_model: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def source_url(self) -> str | None:
        value = self.metadata.get("source_url") or self.metadata.get("url")
        if not value:
            return None
        candidate = str(value).strip()
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return candidate


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    tenant_id: str
    company_id: str
    text: str
    embedding: tuple[float, ...] | None = None
    top_k: int = 6
    candidate_limit: int = 30
    trigram_threshold: float = 0.12
    rrf_k: int = 60
    vector_weight: float = 1.0
    lexical_weight: float = 1.0
    # Public chat always supplies a card.  None preserves compatibility for
    # offline evaluation jobs that intentionally operate at company scope.
    card_id: str | None = None


@dataclass(frozen=True, slots=True)
class ForbiddenTopicPolicy:
    rule_id: str
    topic: str
    match_terms: tuple[str, ...]
    action: Literal["refuse", "handoff", "safe_template"]
    safe_response: str | None = None
    version: int = 1


@dataclass(frozen=True, slots=True)
class RAGRequest:
    tenant_id: str
    company_id: str
    question: str
    company_name: str | None = None
    top_k: int | None = None
    history: tuple[ChatMessage, ...] = ()
    forbidden_topics: tuple[ForbiddenTopicPolicy, ...] = ()
    card_id: str | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    evidence_id: str
    document_id: str
    version_id: str
    ordinal: int
    title: str
    excerpt: str
    source_url: str | None
    content_hash: str | None
    score: float


@dataclass(frozen=True, slots=True)
class Refusal:
    code: RefusalCode
    reason: str
    retryable: bool = False
    safe_alternative: str | None = None


@dataclass(frozen=True, slots=True)
class TraceMetadata:
    trace_id: str
    query_fingerprint: str
    prompt_version: str
    chat_provider: str
    chat_model: str
    embedding_provider: str | None
    embedding_model: str | None
    retrieval_mode: Literal["hybrid", "lexical", "skipped"]
    retrieval_count: int
    citation_count: int
    policy_flags: tuple[str, ...]
    elapsed_ms: int
    retrieval_ms: int = 0
    model_ms: int = 0
    provider_request_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error_category: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AIAnswer:
    answer: str
    citations: tuple[Citation, ...]
    refusal: Refusal | None
    trace: TraceMetadata

    @property
    def refused(self) -> bool:
        return self.refusal is not None


def messages_to_payload(messages: Sequence[ChatMessage]) -> list[dict[str, str]]:
    """Convert immutable messages to the OpenAI-compatible wire shape."""

    return [{"role": message.role, "content": message.content} for message in messages]
