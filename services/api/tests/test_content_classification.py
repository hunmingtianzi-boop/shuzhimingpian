from __future__ import annotations

import json

import pytest

from app.ai import (
    AIErrorCategory,
    AIProviderError,
    ChatCompletion,
    ProviderCredentials,
    StructuredModelAnswer,
)
from app.services.content_classification import (
    ClassificationDocument,
    classify_content_with_hard_gates,
    validate_content_classification,
)

DOCUMENT = ClassificationDocument(
    source_id="doc-1",
    file_name="企业资料.txt",
    content=(
        "星澜智造科技有限公司位于浙江杭州。"
        "核心业务：设备数据接入与协同。"
        "问：是否必须更换设备？答：通常不需要。"
    ),
)


def _payload(*, source_text: str | None = None, industry: str = "") -> dict[str, object]:
    excerpt = source_text or DOCUMENT.content
    return {
        "enterprise_profile": [
            {
                "company_name": "星澜智造科技有限公司",
                "summary": "",
                "industry": industry,
                "region": "浙江杭州",
                "website": "",
                "meta": {
                    "source_id": "doc-1",
                    "source_text": excerpt,
                    "confidence": 0.9,
                },
            }
        ],
        "products": [],
        "case_studies": [],
        "faqs": [],
        "unclassified": [],
    }


def _completion(payload: object) -> ChatCompletion:
    answer = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return ChatCompletion(
        output=StructuredModelAnswer(answer=answer),
        provider="deepseek",
        model="deepseek-v4-flash",
    )


class FakeProvider:
    def __init__(self, *responses: ChatCompletion) -> None:
        self.responses = list(responses)
        self.calls: list[object] = []

    async def complete(self, messages: object, **kwargs: object) -> ChatCompletion:
        self.calls.append((messages, kwargs))
        return self.responses.pop(0)


class FailingProvider:
    async def complete(self, messages: object, **kwargs: object) -> ChatCompletion:
        raise AIProviderError(
            "truncated",
            category=AIErrorCategory.INVALID_RESPONSE,
            code="provider_output_truncated",
        )


def test_accepts_strict_five_category_payload_with_exact_evidence() -> None:
    parsed = validate_content_classification(_payload(), documents=[DOCUMENT])

    assert parsed.enterprise_profile[0].company_name == "星澜智造科技有限公司"
    assert parsed.enterprise_profile[0].meta.source_id == "doc-1"


def test_accepts_pdf_line_wraps_and_restores_exact_source_span() -> None:
    document = ClassificationDocument(
        source_id="doc-1",
        file_name="企业资料.pdf",
        content="星澜智造科技有限公司位于浙江\n杭州。核心业务：设备数据接入与协同。",
    )
    payload = _payload(source_text="星澜智造科技有限公司位于浙江杭州。")

    parsed = validate_content_classification(payload, documents=[document])

    assert parsed.enterprise_profile[0].meta.source_text == (
        "星澜智造科技有限公司位于浙江\n杭州。"
    )


def test_allows_reviewable_faq_rewording_when_evidence_is_exact() -> None:
    payload = {
        **_payload(),
        "enterprise_profile": [],
        "faqs": [
            {
                "question": "现有设备需要全部更换吗？",
                "answer": "一般无需整体更换，优先接入已有设备。",
                "meta": {
                    "source_id": "doc-1",
                    "source_text": "问：是否必须更换设备？答：通常不需要。",
                    "confidence": 0.8,
                },
            }
        ],
    }

    parsed = validate_content_classification(payload, documents=[DOCUMENT])

    assert parsed.faqs[0].question == "现有设备需要全部更换吗？"


def test_rejects_rewording_that_invents_a_numeric_fact() -> None:
    payload = {
        **_payload(),
        "enterprise_profile": [],
        "faqs": [
            {
                "question": "现有设备需要全部更换吗？",
                "answer": "一般无需整体更换，预计 30 天上线。",
                "meta": {
                    "source_id": "doc-1",
                    "source_text": "问：是否必须更换设备？答：通常不需要。",
                    "confidence": 0.8,
                },
            }
        ],
    }

    with pytest.raises(ValueError, match="classification_atomic_field_ungrounded"):
        validate_content_classification(payload, documents=[DOCUMENT])


@pytest.mark.asyncio
async def test_accepts_narrow_markdown_json_fence_compatibility() -> None:
    answer = f"```json\n{json.dumps(_payload(), ensure_ascii=False)}\n```"
    provider = FakeProvider(_completion(answer))

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
    )

    assert result.status == "review"
    assert result.attempts == 1


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({**_payload(), "articles": []}, "classification_schema_invalid"),
        (_payload(source_text="不存在的原文"), "classification_excerpt_not_found"),
        (_payload(industry="智能制造"), "classification_atomic_field_ungrounded"),
    ],
)
def test_rejects_extra_category_fake_excerpt_and_inferred_atomic_fields(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_content_classification(payload, documents=[DOCUMENT])


@pytest.mark.asyncio
async def test_repairs_once_then_returns_review() -> None:
    provider = FakeProvider(_completion("not-json"), _completion(_payload()))

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
    )

    assert result.status == "review"
    assert result.attempts == 2
    assert len(provider.calls) == 2
    second_messages = provider.calls[1][0]
    assert any("修复" in message.content for message in second_messages)


@pytest.mark.asyncio
async def test_two_fake_excerpts_fall_back_to_exact_unclassified_source() -> None:
    provider = FakeProvider(
        _completion(_payload(source_text="伪造来源一")),
        _completion(_payload(source_text="伪造来源二")),
    )

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
    )

    assert result.status == "review"
    assert result.attempts == 2
    assert result.failure_code and result.failure_code.startswith("classification_partial:")
    assert result.classification.enterprise_profile == []
    assert result.classification.unclassified[0].text == DOCUMENT.content
    assert result.classification.unclassified[0].meta.confidence == 0


@pytest.mark.asyncio
async def test_repairs_ungrounded_optional_field_by_clearing_it() -> None:
    invalid = _payload(industry="智能制造")
    provider = FakeProvider(_completion(invalid), _completion(invalid))

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
    )

    assert result.status == "review"
    assert result.classification.enterprise_profile[0].company_name == "星澜智造科技有限公司"
    assert result.classification.enterprise_profile[0].industry == ""
    assert result.failure_code and "classification_recovered" in result.failure_code


@pytest.mark.asyncio
async def test_missing_documents_never_calls_model() -> None:
    provider = FakeProvider()

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[],
    )

    assert result.status == "manual_required"
    assert result.attempts == 0
    assert result.failure_code == "classification_documents_missing"
    assert provider.calls == []


@pytest.mark.asyncio
async def test_large_document_is_chunked_and_duplicate_candidates_are_merged() -> None:
    repeated = "星澜智造科技有限公司位于浙江杭州。\n" * 180
    document = ClassificationDocument(
        source_id="doc-1", file_name="长资料.txt", content=repeated
    )
    candidate = _payload(source_text="星澜智造科技有限公司位于浙江杭州。")
    provider = FakeProvider(*[_completion(candidate) for _ in range(5)])

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
        max_tokens=1_000,
    )

    assert result.status == "review"
    assert len(provider.calls) > 1
    assert len(result.classification.enterprise_profile) == 1


@pytest.mark.asyncio
async def test_provider_truncation_falls_back_to_exact_reviewable_source() -> None:
    result = await classify_content_with_hard_gates(
        provider=FailingProvider(),
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
    )

    assert result.status == "review"
    assert result.failure_code and "classification_fallback" in result.failure_code
    assert result.classification.unclassified[0].text == DOCUMENT.content
