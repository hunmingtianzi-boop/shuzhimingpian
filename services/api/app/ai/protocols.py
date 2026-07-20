"""Dependency-inversion protocols used by the AI subsystem."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from .schemas import (
    ChatCompletion,
    ChatMessage,
    EmbeddingBatch,
    ProviderCredentials,
    RetrievalQuery,
    RetrievedEvidence,
)


@dataclass(frozen=True, slots=True)
class JsonHttpResponse:
    status_code: int
    data: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)


class AsyncJsonTransport(Protocol):
    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> JsonHttpResponse: ...


@runtime_checkable
class AsyncJsonStreamTransport(Protocol):
    def stream_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> AsyncIterator[JsonHttpResponse]: ...


TextDeltaCallback = Callable[[str], Awaitable[None]]


class ChatProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        credentials: ProviderCredentials,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        trace_id: str | None = None,
        on_text_delta: TextDeltaCallback | None = None,
    ) -> ChatCompletion: ...


class EmbeddingProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    async def embed(
        self,
        texts: Sequence[str],
        *,
        credentials: ProviderCredentials,
        trace_id: str | None = None,
    ) -> EmbeddingBatch: ...


class RetrievalRepository(Protocol):
    async def search(self, query: RetrievalQuery) -> Sequence[RetrievedEvidence]: ...


class FAQMatchRepository(Protocol):
    async def find_faq_match(
        self,
        query: RetrievalQuery,
        *,
        similarity_threshold: float,
    ) -> RetrievedEvidence | None: ...


class FAQAnswerCache(Protocol):
    async def get(self, query: RetrievalQuery) -> RetrievedEvidence | None: ...

    async def put(self, query: RetrievalQuery, evidence: RetrievedEvidence) -> None: ...


class AsyncSqlExecutor(Protocol):
    """Minimal SQL execution boundary, easy to fake in unit tests."""

    async def fetch_mappings(
        self,
        statement: Any,
        parameters: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]: ...
