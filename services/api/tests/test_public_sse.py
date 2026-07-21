from __future__ import annotations

import asyncio
import uuid

from app.api.routes.public_conversations import _answer_events
from app.services.public_store import (
    StoredAnswer,
    StoredCitation,
    _looks_like_opportunity,
)


def test_commercial_intent_is_actionable_even_without_a_grounded_answer() -> None:
    assert _looks_like_opportunity("怎么跟析境科技合作？") is True
    assert _looks_like_opportunity("我想了解采购方案") is True
    assert _looks_like_opportunity("你们有哪些业务？") is False


async def test_answer_events_replays_persisted_answer_with_citations() -> None:
    message_id = uuid.uuid4()
    answer = StoredAnswer(
        message_id=message_id,
        text="这是有证据的回答。",
        finish_reason="stop",
        citations=(
            StoredCitation(
                id=uuid.uuid4(),
                label="企业资料",
                source_type="faq",
            ),
        ),
    )

    chunks = [
        chunk.decode("utf-8")
        async for chunk in _answer_events(
            message_id=message_id,
            request_id="request-1",
            stored=answer,
            task=None,
        )
    ]
    body = "".join(chunks)

    assert "event: message.started" in body
    assert "event: message.delta" in body
    assert "event: message.citation" in body
    assert "event: message.completed" in body
    assert body.index("message.delta") < body.index("message.citation")


async def test_answer_events_emits_live_delta_before_generation_finishes() -> None:
    message_id = uuid.uuid4()
    release_generation = asyncio.Event()
    delta_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def finish_generation() -> StoredAnswer:
        await release_generation.wait()
        return StoredAnswer(
            message_id=message_id,
            text="第一段第二段",
            finish_reason="stop",
            citations=(),
        )

    task = asyncio.create_task(finish_generation())
    events = _answer_events(
        message_id=message_id,
        request_id="request-live-1",
        stored=None,
        task=task,
        delta_queue=delta_queue,
    )

    started = (await anext(events)).decode("utf-8")
    await delta_queue.put("第一段")
    first_delta = (await asyncio.wait_for(anext(events), timeout=0.2)).decode("utf-8")

    assert "event: message.started" in started
    assert "event: message.delta" in first_delta
    assert "第一段" in first_delta
    assert not task.done()

    release_generation.set()
    delta_queue.put_nowait(None)
    remainder = "".join([chunk.decode("utf-8") async for chunk in events])

    assert "第二段" in remainder
    assert "event: message.completed" in remainder
