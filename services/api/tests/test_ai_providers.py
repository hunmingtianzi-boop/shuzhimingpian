from __future__ import annotations

import json
from typing import Any, Mapping

import httpx
import pytest

from app.ai import (
    AIErrorCategory,
    AIProviderError,
    ChatMessage,
    ChatProviderConfig,
    EmbeddingProviderConfig,
    HttpxJsonTransport,
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
    ProviderCredentials,
    StructuredOutputMode,
)
from app.ai.protocols import JsonHttpResponse


class FakeTransport:
    def __init__(
        self,
        response: JsonHttpResponse | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


class SequentialTransport(FakeTransport):
    def __init__(self, responses: list[JsonHttpResponse]) -> None:
        super().__init__()
        self.responses = responses

    async def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout_seconds: float,
    ) -> JsonHttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": dict(payload),
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.responses.pop(0)


def _credentials() -> ProviderCredentials:
    return ProviderCredentials(api_key="-".join(["unit", "test", "credential"]))


@pytest.mark.asyncio
async def test_http_transport_keeps_short_connect_and_pool_timeouts() -> None:
    seen_timeout: dict[str, float] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_timeout.update(request.extensions["timeout"])
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        transport = HttpxJsonTransport(client)
        response = await transport.post_json(
            url="https://provider.example.test/v1/chat/completions",
            headers={},
            payload={},
            timeout_seconds=17.0,
        )

    assert response.status_code == 200
    assert seen_timeout == {
        "connect": 5.0,
        "read": 17.0,
        "write": 17.0,
        "pool": 5.0,
    }


@pytest.mark.asyncio
async def test_deepseek_defaults_and_structured_chat_request_hide_credentials() -> None:
    content = json.dumps(
        {
            "answer": "企业成立于 2024 年。",
            "cited_evidence_ids": ["chunk-1"],
            "refusal_reason": None,
            "needs_human_review": False,
        },
        ensure_ascii=False,
    )
    transport = FakeTransport(
        JsonHttpResponse(
            200,
            {
                "id": "completion-1",
                "model": "deepseek-v4-flash",
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 8, "total_tokens": 18},
            },
            {"x-request-id": "request-1"},
        )
    )
    config = ChatProviderConfig()
    provider = OpenAICompatibleChatProvider(config, transport=transport)
    credentials = _credentials()

    result = await provider.complete(
        [ChatMessage(role="user", content="公司什么时候成立？")],
        credentials=credentials,
        trace_id="trace-1",
    )

    assert config.base_url == "https://api.deepseek.com"
    assert config.model == "deepseek-v4-flash"
    assert result.output.answer == "企业成立于 2024 年。"
    assert result.output.cited_evidence_ids == ["chunk-1"]
    assert result.request_id == "request-1"
    assert result.usage.total_tokens == 18
    call = transport.calls[0]
    assert call["url"] == "https://api.deepseek.com/chat/completions"
    assert call["payload"]["thinking"] == {"type": "disabled"}
    assert call["payload"]["response_format"] == {"type": "json_object"}
    assert call["headers"]["X-Client-Trace-Id"] == "trace-1"
    assert call["headers"]["Authorization"].startswith("Bearer unit-test-")
    assert "unit-test-credential" not in repr(credentials)
    assert "unit-test-credential" not in repr(provider)


@pytest.mark.asyncio
async def test_chat_provider_accepts_structured_answer_presentation() -> None:
    content = json.dumps(
        {
            "answer": "",
            "presentation": {
                "lead": "企业主要提供两类服务。",
                "lead_emphasis": ["两类服务"],
                "blocks": [
                    {
                        "type": "bullets",
                        "title": "服务类型",
                        "text": None,
                        "items": [
                            {"label": "人才服务", "text": None},
                            {"label": "场景服务", "text": None},
                        ],
                    }
                ],
            },
            "cited_evidence_ids": ["chunk-1"],
            "refusal_reason": None,
            "needs_human_review": False,
        },
        ensure_ascii=False,
    )
    transport = FakeTransport(
        JsonHttpResponse(
            200,
            {"choices": [{"message": {"role": "assistant", "content": content}}]},
        )
    )
    provider = OpenAICompatibleChatProvider(ChatProviderConfig(), transport=transport)

    result = await provider.complete(
        [ChatMessage(role="user", content="主要有哪些服务？")],
        credentials=_credentials(),
    )

    assert result.output.answer == ""
    assert result.output.presentation is not None
    assert result.output.presentation.lead_emphasis == ["两类服务"]
    assert result.output.presentation.blocks[0].title == "服务类型"
    system_copy = transport.calls[0]["payload"]["messages"][0]["content"]
    assert '"presentation": null' in system_copy
    assert '"answer_emphasis": []' in system_copy
    assert "complete user-facing answer as GitHub Flavored Markdown" in system_copy
    assert "compatibility path for a new response" in system_copy


@pytest.mark.asyncio
async def test_invalid_presentation_falls_back_to_complete_answer() -> None:
    content = json.dumps(
        {
            "answer": "企业主要提供人才服务和场景服务。",
            "presentation": {
                "lead": "企业主要提供两类服务。",
                "blocks": [
                    {
                        "type": "bullets",
                        "title": None,
                        "items": [{"text": "只有一个项目"}],
                    }
                ],
            },
            "cited_evidence_ids": [],
            "refusal_reason": None,
            "needs_human_review": False,
        },
        ensure_ascii=False,
    )
    transport = FakeTransport(
        JsonHttpResponse(
            200,
            {"choices": [{"message": {"role": "assistant", "content": content}}]},
        )
    )
    provider = OpenAICompatibleChatProvider(ChatProviderConfig(), transport=transport)

    result = await provider.complete(
        [ChatMessage(role="user", content="主要有哪些服务？")],
        credentials=_credentials(),
    )

    assert result.output.answer == "企业主要提供人才服务和场景服务。"
    assert result.output.presentation is None


@pytest.mark.asyncio
async def test_openai_json_schema_mode_can_disable_deepseek_thinking_field() -> None:
    transport = FakeTransport(
        JsonHttpResponse(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "parsed": {
                                "answer": "Grounded",
                                "cited_evidence_ids": ["ev-1"],
                                "refusal_reason": None,
                                "needs_human_review": False,
                            }
                        }
                    }
                ]
            },
        )
    )
    provider = OpenAICompatibleChatProvider(
        ChatProviderConfig(
            base_url="https://api.openai.com/v1",
            model="gpt-test",
            provider_name="openai",
            output_mode=StructuredOutputMode.JSON_SCHEMA,
            thinking_mode=None,
        ),
        transport=transport,
    )

    await provider.complete(
        [ChatMessage(role="user", content="question")],
        credentials=_credentials(),
    )

    payload = transport.calls[0]["payload"]
    assert "thinking" not in payload
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "category", "retryable"),
    [
        (401, AIErrorCategory.AUTHENTICATION, False),
        (402, AIErrorCategory.BILLING, False),
        (403, AIErrorCategory.PERMISSION, False),
        (429, AIErrorCategory.RATE_LIMIT, True),
        (500, AIErrorCategory.UPSTREAM_UNAVAILABLE, True),
        (504, AIErrorCategory.TIMEOUT, True),
    ],
)
async def test_provider_classifies_http_errors_without_response_body(
    status: int,
    category: AIErrorCategory,
    retryable: bool,
) -> None:
    transport = FakeTransport(
        JsonHttpResponse(status, {"error": {"message": "body must stay private"}})
    )
    provider = OpenAICompatibleChatProvider(ChatProviderConfig(), transport=transport)

    with pytest.raises(AIProviderError) as captured:
        await provider.complete(
            [ChatMessage(role="user", content="question")],
            credentials=_credentials(),
        )

    assert captured.value.category is category
    assert captured.value.retryable is retryable
    assert "body must stay private" not in str(captured.value)
    assert "unit-test-credential" not in repr(captured.value)


@pytest.mark.asyncio
async def test_provider_classifies_transport_timeout() -> None:
    provider = OpenAICompatibleChatProvider(
        ChatProviderConfig(),
        transport=FakeTransport(error=TimeoutError()),
    )

    with pytest.raises(AIProviderError) as captured:
        await provider.complete(
            [ChatMessage(role="user", content="question")],
            credentials=_credentials(),
        )

    assert captured.value.category is AIErrorCategory.TIMEOUT
    assert captured.value.retryable is True


@pytest.mark.asyncio
async def test_embedding_provider_orders_vectors_and_validates_dimensions() -> None:
    transport = FakeTransport(
        JsonHttpResponse(
            200,
            {
                "model": "embedding-test",
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ],
                "usage": {"prompt_tokens": 5, "total_tokens": 5},
            },
            {"x-request-id": "embedding-request"},
        )
    )
    provider = OpenAICompatibleEmbeddingProvider(
        EmbeddingProviderConfig(
            base_url="https://embedding.example/v1",
            model="embedding-test",
            dimensions=3,
        ),
        transport=transport,
    )

    result = await provider.embed(
        ["first", "second"],
        credentials=_credentials(),
    )

    assert result.embeddings == ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6))
    assert result.request_id == "embedding-request"
    assert transport.calls[0]["url"] == "https://embedding.example/v1/embeddings"
    assert transport.calls[0]["payload"]["dimensions"] == 3


@pytest.mark.asyncio
async def test_invalid_structured_response_has_stable_classification() -> None:
    provider = OpenAICompatibleChatProvider(
        ChatProviderConfig(),
        transport=FakeTransport(
            JsonHttpResponse(
                200,
                {"choices": [{"message": {"content": "not-json"}}]},
            )
        ),
    )

    with pytest.raises(AIProviderError) as captured:
        await provider.complete(
            [ChatMessage(role="user", content="question")],
            credentials=_credentials(),
        )

    assert captured.value.category is AIErrorCategory.INVALID_RESPONSE
    assert captured.value.code == "invalid_chat_response"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "category", "retryable"),
    [
        ("length", AIErrorCategory.INVALID_RESPONSE, False),
        ("content_filter", AIErrorCategory.SAFETY, False),
        ("insufficient_system_resource", AIErrorCategory.UPSTREAM_UNAVAILABLE, True),
    ],
)
async def test_provider_classifies_success_status_finish_failures(
    finish_reason: str,
    category: AIErrorCategory,
    retryable: bool,
) -> None:
    provider = OpenAICompatibleChatProvider(
        ChatProviderConfig(),
        transport=FakeTransport(
            JsonHttpResponse(
                200,
                {
                    "choices": [
                        {
                            "finish_reason": finish_reason,
                            "message": {"content": "{}"},
                        }
                    ]
                },
            )
        ),
    )

    with pytest.raises(AIProviderError) as captured:
        await provider.complete(
            [ChatMessage(role="user", content="question")],
            credentials=_credentials(),
        )

    assert captured.value.category is category
    assert captured.value.retryable is retryable


@pytest.mark.asyncio
async def test_thinking_request_uses_reasoning_effort_without_temperature() -> None:
    content = json.dumps(
        {
            "answer": "Grounded",
            "cited_evidence_ids": ["chunk-1"],
            "refusal_reason": None,
            "needs_human_review": False,
        }
    )
    transport = FakeTransport(
        JsonHttpResponse(
            200,
            {"choices": [{"finish_reason": "stop", "message": {"content": content}}]},
        )
    )
    provider = OpenAICompatibleChatProvider(
        ChatProviderConfig(thinking_mode="enabled", reasoning_effort="high"),
        transport=transport,
    )

    await provider.complete(
        [ChatMessage(role="user", content="question")],
        credentials=_credentials(),
    )

    payload = transport.calls[0]["payload"]
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["reasoning_effort"] == "high"
    assert "temperature" not in payload


@pytest.mark.asyncio
async def test_json_mode_retries_one_empty_response() -> None:
    valid = json.dumps(
        {
            "answer": "Grounded",
            "cited_evidence_ids": ["chunk-1"],
            "refusal_reason": None,
            "needs_human_review": False,
        }
    )
    transport = SequentialTransport(
        [
            JsonHttpResponse(
                200,
                {"choices": [{"finish_reason": "stop", "message": {"content": ""}}]},
            ),
            JsonHttpResponse(
                200,
                {"choices": [{"finish_reason": "stop", "message": {"content": valid}}]},
            ),
        ]
    )
    provider = OpenAICompatibleChatProvider(ChatProviderConfig(), transport=transport)

    result = await provider.complete(
        [ChatMessage(role="user", content="question")],
        credentials=_credentials(),
    )

    assert result.output.answer == "Grounded"
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_json_mode_repairs_one_invalid_presentation_without_losing_usage() -> None:
    invalid = json.dumps(
        {
            "answer": "",
            "presentation": {
                "lead": "企业有两类服务。",
                "blocks": [
                    {
                        "type": "bullets",
                        "title": None,
                        "items": [{"text": "只有一个无标签项目"}],
                    }
                ],
            },
        },
        ensure_ascii=False,
    )
    repaired = json.dumps(
        {
            "answer": "",
            "presentation": {
                "lead": "企业主要提供人才服务和场景服务。",
                "lead_emphasis": ["人才服务", "场景服务"],
                "blocks": [],
            },
        },
        ensure_ascii=False,
    )
    transport = SequentialTransport(
        [
            JsonHttpResponse(
                200,
                {
                    "choices": [{"finish_reason": "stop", "message": {"content": invalid}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 8,
                        "total_tokens": 18,
                    },
                },
            ),
            JsonHttpResponse(
                200,
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": repaired}}
                    ],
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 9,
                        "total_tokens": 29,
                    },
                },
            ),
        ]
    )
    provider = OpenAICompatibleChatProvider(ChatProviderConfig(), transport=transport)

    result = await provider.complete(
        [ChatMessage(role="user", content="主要有哪些服务？")],
        credentials=_credentials(),
    )

    assert result.output.presentation is not None
    assert result.output.presentation.lead_emphasis == ["人才服务", "场景服务"]
    assert result.usage.input_tokens == 30
    assert result.usage.output_tokens == 17
    assert result.usage.total_tokens == 47
    assert len(transport.calls) == 2
    repair_messages = transport.calls[1]["payload"]["messages"]
    assert repair_messages[-2]["role"] == "assistant"
    assert repair_messages[-1]["role"] == "user"
    assert "same factual content" in repair_messages[-1]["content"]
