"""DeepSeek/OpenAI-compatible chat and embedding providers.

Credentials are intentionally accepted only on each call.  Provider instances
hold endpoint/model configuration, but never retain or log a caller's secret.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .errors import AIErrorCategory, AIProviderError
from .protocols import AsyncJsonTransport, JsonHttpResponse
from .schemas import (
    ChatCompletion,
    ChatMessage,
    EmbeddingBatch,
    ProviderCredentials,
    StructuredModelAnswer,
    StructuredOutputMode,
    TokenUsage,
    messages_to_payload,
)

_STRUCTURED_OUTPUT_INSTRUCTION = """
Return only one valid JSON object. It must match this exact shape:
{
  "answer": "the complete user-facing answer as GitHub Flavored Markdown",
  "answer_emphasis": [],
  "presentation": null,
  "cited_evidence_ids": ["evidence ids used by the answer"],
  "refusal_reason": null,
  "needs_human_review": false
}
Always put the complete user-facing response in answer. The model may freely
choose concise headings, paragraphs, lists, blockquotes, GFM tables, and fenced
Mermaid diagrams according to the content. Use tables only for actual comparison
or repeated labelled data. Use Mermaid only when a process, hierarchy,
dependency, or branch is materially clearer as a diagram. Keep diagrams compact
and mobile-readable. Set answer_emphasis to an empty array and presentation to
null. Older stored responses may still contain presentation data, but never use
that compatibility path for a new response.
Use refusal_reason only when the request cannot be answered safely. Ordinary
conversation may omit evidence only when the server payload explicitly sets
general_answer_allowed to true. Never wrap the JSON in Markdown fences.
""".strip()

_STRUCTURED_OUTPUT_REPAIR_INSTRUCTION = """
The previous JSON object did not match the required response schema. Reformat
the same factual content only; do not add, remove, or reinterpret claims. Put
the complete user-facing Markdown in answer, preserve its useful formatting,
set answer_emphasis to an empty array and presentation to null, and use only the
documented fields. Return only the corrected JSON object.
""".strip()


def _validate_base_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url must not contain credentials, query, or fragment")
    return normalized


def _validate_structured_answer(value: object) -> StructuredModelAnswer:
    """Prefer validated blocks, but keep a complete text answer as fallback."""

    try:
        return StructuredModelAnswer.model_validate(value)
    except ValidationError:
        if not isinstance(value, Mapping):
            raise
        answer = value.get("answer")
        if not isinstance(answer, str) or not answer.strip() or value.get("presentation") is None:
            raise
        fallback = dict(value)
        fallback["presentation"] = None
        return StructuredModelAnswer.model_validate(fallback)


@dataclass(frozen=True, slots=True)
class ChatProviderConfig:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    provider_name: str = "deepseek"
    timeout_seconds: float = 30.0
    output_mode: StructuredOutputMode = StructuredOutputMode.JSON_OBJECT
    thinking_mode: Literal["enabled", "disabled"] | None = "disabled"
    reasoning_effort: Literal["high", "max"] | None = None
    max_retries: int = 2
    retry_base_delay_seconds: float = 0.05

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url))
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not self.provider_name.strip():
            raise ValueError("provider_name must not be empty")
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be between 0 and 300")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("max_retries must be between 0 and 5")
        if not 0 <= self.retry_base_delay_seconds <= 5:
            raise ValueError("retry_base_delay_seconds must be between 0 and 5")

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"


@dataclass(frozen=True, slots=True)
class EmbeddingProviderConfig:
    base_url: str
    model: str
    provider_name: str = "openai-compatible-embedding"
    timeout_seconds: float = 30.0
    dimensions: int | None = None
    max_batch_size: int = 128

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", _validate_base_url(self.base_url))
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not self.provider_name.strip():
            raise ValueError("provider_name must not be empty")
        if not 0 < self.timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be between 0 and 300")
        if self.dimensions is not None and self.dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if not 1 <= self.max_batch_size <= 2048:
            raise ValueError("max_batch_size must be between 1 and 2048")

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/embeddings"


class HttpxJsonTransport:
    """Small httpx adapter; inject an AsyncClient to control its lifecycle."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        # A per-request float timeout overrides the client's timeout settings.
        # Keep the model's read budget, while failing a broken provider
        # connection or exhausted connection pool quickly.  Without this, a
        # failed TCP/TLS connection can consume the full model timeout for each
        # retry and make a chat request appear to hang.
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(5.0, timeout_seconds),
            pool=min(5.0, timeout_seconds),
        )
        if self._client is not None:
            response = await self._client.post(
                url,
                headers=dict(headers),
                json=dict(payload),
                timeout=timeout,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=dict(headers),
                    json=dict(payload),
                    timeout=timeout,
                )

        try:
            decoded = response.json()
        except ValueError:
            decoded = {"_invalid_json": True}
        if not isinstance(decoded, Mapping):
            decoded = {"_non_object_json": True}
        return JsonHttpResponse(
            status_code=response.status_code,
            data=decoded,
            headers=dict(response.headers),
        )


class OpenAICompatibleChatProvider:
    """Strict structured chat client for DeepSeek or any OpenAI-compatible API."""

    def __init__(
        self,
        config: ChatProviderConfig,
        *,
        transport: AsyncJsonTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or HttpxJsonTransport()

    @property
    def provider_name(self) -> str:
        return self.config.provider_name

    @property
    def model_name(self) -> str:
        return self.config.model

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        credentials: ProviderCredentials,
        temperature: float = 0.1,
        max_tokens: int = 1200,
        trace_id: str | None = None,
    ) -> ChatCompletion:
        if not messages:
            raise ValueError("messages must not be empty")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be positive")

        wire_messages = [
            ChatMessage(role="system", content=_STRUCTURED_OUTPUT_INSTRUCTION),
            *messages,
        ]
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages_to_payload(wire_messages),
            "max_tokens": max_tokens,
            "stream": False,
        }
        if self.config.thinking_mode != "enabled":
            payload["temperature"] = temperature
        if self.config.thinking_mode is not None:
            payload["thinking"] = {"type": self.config.thinking_mode}
        if self.config.thinking_mode == "enabled" and self.config.reasoning_effort:
            payload["reasoning_effort"] = self.config.reasoning_effort
        if self.config.output_mode is StructuredOutputMode.JSON_OBJECT:
            payload["response_format"] = {"type": "json_object"}
        elif self.config.output_mode is StructuredOutputMode.JSON_SCHEMA:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "grounded_answer",
                    "strict": True,
                    "schema": StructuredModelAnswer.model_json_schema(),
                },
            }

        response: JsonHttpResponse | None = None
        provider_attempt = 0
        empty_json_retry_used = False
        structured_repair_used = False
        accumulated_usage = TokenUsage()
        while True:
            try:
                response = await self._request(
                    url=self.config.endpoint,
                    credentials=credentials,
                    payload=payload,
                    timeout_seconds=self.config.timeout_seconds,
                    trace_id=trace_id,
                )
                self._raise_for_status(response)
                _raise_for_finish_reason(response)
            except AIProviderError as exc:
                if exc.retryable and provider_attempt < self.config.max_retries:
                    delay = self.config.retry_base_delay_seconds * (2**provider_attempt)
                    delay *= 0.75 + random.random() * 0.5  # noqa: S311 - jitter only
                    provider_attempt += 1
                    await asyncio.sleep(delay)
                    continue
                raise

            raw_output: object | None = None
            try:
                current_usage = _parse_usage(response.data.get("usage"))
                raw_output = _extract_structured_chat_content(response.data)
                output = _validate_structured_answer(raw_output)
                usage = _sum_token_usage(accumulated_usage, current_usage)
                response_model = str(response.data.get("model") or self.config.model)
                break
            except (KeyError, TypeError, ValueError, ValidationError) as exc:
                if not empty_json_retry_used and _has_empty_message_content(response.data):
                    empty_json_retry_used = True
                    accumulated_usage = _sum_token_usage(
                        accumulated_usage,
                        _parse_usage(response.data.get("usage")),
                    )
                    continue
                if not structured_repair_used and isinstance(raw_output, Mapping):
                    structured_repair_used = True
                    accumulated_usage = _sum_token_usage(
                        accumulated_usage,
                        _parse_usage(response.data.get("usage")),
                    )
                    repair_messages = [
                        *wire_messages,
                        ChatMessage(
                            role="assistant",
                            content=json.dumps(raw_output, ensure_ascii=False),
                        ),
                        ChatMessage(
                            role="user",
                            content=_STRUCTURED_OUTPUT_REPAIR_INSTRUCTION,
                        ),
                    ]
                    payload["messages"] = messages_to_payload(repair_messages)
                    continue
                raise AIProviderError(
                    "Provider returned an invalid structured chat response.",
                    category=AIErrorCategory.INVALID_RESPONSE,
                    code="invalid_chat_response",
                    retryable=False,
                    status_code=response.status_code,
                    request_id=_request_id(response),
                ) from exc
        assert response is not None

        return ChatCompletion(
            output=output,
            provider=self.config.provider_name,
            model=response_model,
            request_id=_request_id(response),
            usage=usage,
        )

    async def _request(
        self,
        *,
        url: str,
        credentials: ProviderCredentials,
        payload: Mapping[str, Any],
        timeout_seconds: float,
        trace_id: str | None,
    ) -> JsonHttpResponse:
        headers = {
            "Authorization": credentials.authorization_value(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if trace_id:
            headers["X-Client-Trace-Id"] = trace_id
        try:
            return await self._transport.post_json(
                url=url,
                headers=headers,
                payload=payload,
                timeout_seconds=timeout_seconds,
            )
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise AIProviderError(
                "AI provider request timed out.",
                category=AIErrorCategory.TIMEOUT,
                code="provider_timeout",
                retryable=True,
            ) from exc
        except (httpx.NetworkError, httpx.HTTPError, OSError) as exc:
            raise AIProviderError(
                "AI provider is temporarily unavailable.",
                category=AIErrorCategory.UPSTREAM_UNAVAILABLE,
                code="provider_network_error",
                retryable=True,
            ) from exc

    @staticmethod
    def _raise_for_status(response: JsonHttpResponse) -> None:
        _raise_for_provider_status(response)


class OpenAICompatibleEmbeddingProvider:
    """Optional independent embedding client using the same wire protocol."""

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        *,
        transport: AsyncJsonTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport or HttpxJsonTransport()

    @property
    def provider_name(self) -> str:
        return self.config.provider_name

    @property
    def model_name(self) -> str:
        return self.config.model

    async def embed(
        self,
        texts: Sequence[str],
        *,
        credentials: ProviderCredentials,
        trace_id: str | None = None,
    ) -> EmbeddingBatch:
        if not texts:
            raise ValueError("texts must not be empty")
        if len(texts) > self.config.max_batch_size:
            raise ValueError("embedding batch exceeds max_batch_size")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("embedding texts must be non-empty strings")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": list(texts),
            "encoding_format": "float",
        }
        if self.config.dimensions is not None:
            payload["dimensions"] = self.config.dimensions

        chat_request_adapter = OpenAICompatibleChatProvider(
            ChatProviderConfig(
                base_url=self.config.base_url,
                model=self.config.model,
                provider_name=self.config.provider_name,
                timeout_seconds=self.config.timeout_seconds,
            ),
            transport=self._transport,
        )
        response = await chat_request_adapter._request(
            url=self.config.endpoint,
            credentials=credentials,
            payload=payload,
            timeout_seconds=self.config.timeout_seconds,
            trace_id=trace_id,
        )
        _raise_for_provider_status(response)

        try:
            raw_items = response.data["data"]
            if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
                raise TypeError("data must be an array")
            indexed: list[tuple[int, tuple[float, ...]]] = []
            for item in raw_items:
                if not isinstance(item, Mapping):
                    raise TypeError("embedding item must be an object")
                index = int(item["index"])
                raw_vector = item["embedding"]
                if not isinstance(raw_vector, Sequence) or isinstance(raw_vector, (str, bytes)):
                    raise TypeError("embedding must be an array")
                vector = tuple(float(value) for value in raw_vector)
                if not vector or any(not math.isfinite(value) for value in vector):
                    raise ValueError("embedding contains invalid values")
                if self.config.dimensions is not None and len(vector) != self.config.dimensions:
                    raise ValueError("embedding dimension mismatch")
                indexed.append((index, vector))
            indexed.sort(key=lambda pair: pair[0])
            if [index for index, _ in indexed] != list(range(len(texts))):
                raise ValueError("embedding indices are missing or duplicated")
            embeddings = tuple(vector for _, vector in indexed)
            usage = _parse_usage(response.data.get("usage"))
            response_model = str(response.data.get("model") or self.config.model)
        except (KeyError, TypeError, ValueError) as exc:
            raise AIProviderError(
                "Provider returned an invalid embedding response.",
                category=AIErrorCategory.INVALID_RESPONSE,
                code="invalid_embedding_response",
                retryable=False,
                status_code=response.status_code,
                request_id=_request_id(response),
            ) from exc

        return EmbeddingBatch(
            embeddings=embeddings,
            provider=self.config.provider_name,
            model=response_model,
            request_id=_request_id(response),
            usage=usage,
        )


def _extract_structured_chat_content(data: Mapping[str, Any]) -> Mapping[str, Any]:
    choices = data["choices"]
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
        raise TypeError("choices must be a non-empty array")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise TypeError("choice must be an object")
    message = first["message"]
    if not isinstance(message, Mapping):
        raise TypeError("message must be an object")
    parsed = message.get("parsed")
    if isinstance(parsed, Mapping):
        return parsed
    content = message["content"]
    if isinstance(content, Mapping):
        return content
    if not isinstance(content, str):
        raise TypeError("message content must be text or an object")
    cleaned = content.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            cleaned = "\n".join(lines[1:-1]).strip()
    decoded = json.loads(cleaned)
    if not isinstance(decoded, Mapping):
        raise TypeError("structured response must be an object")
    return decoded


def _has_empty_message_content(data: Mapping[str, Any]) -> bool:
    choices = data.get("choices")
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
        return False
    first = choices[0]
    if not isinstance(first, Mapping):
        return False
    message = first.get("message")
    if not isinstance(message, Mapping):
        return False
    content = message.get("content")
    return content is None or (isinstance(content, str) and not content.strip())


def _parse_usage(raw_usage: Any) -> TokenUsage:
    if not isinstance(raw_usage, Mapping):
        return TokenUsage()
    input_tokens = int(raw_usage.get("prompt_tokens") or raw_usage.get("input_tokens") or 0)
    output_tokens = int(raw_usage.get("completion_tokens") or raw_usage.get("output_tokens") or 0)
    total_tokens = int(raw_usage.get("total_tokens") or input_tokens + output_tokens)
    return TokenUsage(
        input_tokens=max(input_tokens, 0),
        output_tokens=max(output_tokens, 0),
        total_tokens=max(total_tokens, 0),
    )


def _sum_token_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def _request_id(response: JsonHttpResponse) -> str | None:
    for key, value in response.headers.items():
        if key.lower() in {"x-request-id", "request-id", "x-amzn-requestid"}:
            return str(value)
    value = response.data.get("id")
    return str(value) if value else None


def _raise_for_provider_status(response: JsonHttpResponse) -> None:
    status = response.status_code
    if 200 <= status < 300:
        return

    request_id = _request_id(response)
    if status == 401:
        category, code, message, retryable = (
            AIErrorCategory.AUTHENTICATION,
            "provider_authentication_failed",
            "AI provider authentication failed.",
            False,
        )
    elif status == 402:
        category, code, message, retryable = (
            AIErrorCategory.BILLING,
            "provider_balance_exhausted",
            "AI provider balance is insufficient.",
            False,
        )
    elif status == 403:
        category, code, message, retryable = (
            AIErrorCategory.PERMISSION,
            "provider_permission_denied",
            "AI provider permission denied.",
            False,
        )
    elif status == 429:
        category, code, message, retryable = (
            AIErrorCategory.RATE_LIMIT,
            "provider_rate_limited",
            "AI provider rate limit exceeded.",
            True,
        )
    elif status in {408, 504}:
        category, code, message, retryable = (
            AIErrorCategory.TIMEOUT,
            "provider_timeout",
            "AI provider request timed out.",
            True,
        )
    elif 500 <= status <= 599:
        category, code, message, retryable = (
            AIErrorCategory.UPSTREAM_UNAVAILABLE,
            "provider_unavailable",
            "AI provider is temporarily unavailable.",
            True,
        )
    else:
        category, code, message, retryable = (
            AIErrorCategory.INVALID_REQUEST,
            "provider_rejected_request",
            "AI provider rejected the request.",
            False,
        )
    raise AIProviderError(
        message,
        category=category,
        code=code,
        retryable=retryable,
        status_code=status,
        request_id=request_id,
    )


def _raise_for_finish_reason(response: JsonHttpResponse) -> None:
    choices = response.data.get("choices")
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)) or not choices:
        return
    first = choices[0]
    if not isinstance(first, Mapping):
        return
    finish_reason = first.get("finish_reason")
    if finish_reason in {None, "stop"}:
        return
    request_id = _request_id(response)
    if finish_reason == "content_filter":
        raise AIProviderError(
            "AI provider filtered the response.",
            category=AIErrorCategory.SAFETY,
            code="provider_content_filtered",
            retryable=False,
            status_code=response.status_code,
            request_id=request_id,
        )
    if finish_reason == "insufficient_system_resource":
        raise AIProviderError(
            "AI provider lacks inference capacity.",
            category=AIErrorCategory.UPSTREAM_UNAVAILABLE,
            code="provider_insufficient_resource",
            retryable=True,
            status_code=response.status_code,
            request_id=request_id,
        )
    if finish_reason == "length":
        raise AIProviderError(
            "AI provider output was truncated.",
            category=AIErrorCategory.INVALID_RESPONSE,
            code="provider_output_truncated",
            retryable=False,
            status_code=response.status_code,
            request_id=request_id,
        )
    raise AIProviderError(
        "AI provider returned an unsupported finish reason.",
        category=AIErrorCategory.INVALID_RESPONSE,
        code="provider_finish_reason_unsupported",
        retryable=False,
        status_code=response.status_code,
        request_id=request_id,
    )
