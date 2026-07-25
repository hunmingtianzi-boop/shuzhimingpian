from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.topic_analysis import (
    TopicAnalysisProvider,
    TopicGeneration,
    TopicQuestion,
    _build_view,
    _safe_topic,
)


def test_build_view_aggregates_assignments_and_falls_back_for_missing_topics() -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    third_id = uuid.uuid4()
    now = datetime.now(UTC)
    questions = [
        TopicQuestion(first_id, "怎么报名浙客松？", now),
        TopicQuestion(second_id, "赛事有哪些参赛条件？", now),
        TopicQuestion(third_id, "你们在哪里办公？", now),
    ]
    generation = TopicGeneration(
        summary="用户主要关注赛事参与方式。",
        assignments=(
            (0, "赛事报名"),
            (1, "赛事报名"),
            (1, "重复分配"),
            (9, "未知问题"),
        ),
        provider="deepseek",
        model="deepseek-chat",
        latency_ms=120,
    )

    view = _build_view(
        questions=questions,
        question_count=8,
        period_days=30,
        generation=generation,
    )

    assert view.status == "ready"
    assert view.question_count == 8
    assert view.analyzed_question_count == 3
    assert [(item.topic, item.count) for item in view.topics] == [
        ("赛事报名", 2),
        ("其他问题", 1),
    ]
    assert view.topics[0].share == pytest.approx(0.6667)
    assert view.topics[0].sample_questions == [
        "怎么报名浙客松？",
        "赛事有哪些参赛条件？",
    ]


def test_safe_topic_normalizes_whitespace_and_empty_values() -> None:
    assert _safe_topic("  项目   孵化，") == "项目 孵化"
    assert _safe_topic("  ，；：") == "其他问题"


@pytest.mark.asyncio
async def test_topic_provider_uses_compact_ordered_topics_and_redacts_input() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "deepseek-test",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "用户主要关注赛事报名。",
                                    "topics": ["赛事报名", "赛事报名"],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
            },
        )

    settings = Settings(
        _env_file=None,
        app_env="test",
        llm_api_key=SecretStr("unit-test-provider-key"),
        llm_max_retries=0,
    )
    questions = [
        TopicQuestion(uuid.uuid4(), "电话 13800138000，怎么报名？", datetime.now(UTC)),
        TopicQuestion(uuid.uuid4(), "参赛有什么条件？", datetime.now(UTC)),
    ]
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TopicAnalysisProvider(settings, client).generate(questions)

    payload = json.loads(requests[0].content)
    assert "13800138000" not in json.dumps(payload, ensure_ascii=False)
    assert payload["messages"][1]["content"].startswith('{"questions":[')
    assert result.assignments == ((0, "赛事报名"), (1, "赛事报名"))
    assert result.model == "deepseek-test"
