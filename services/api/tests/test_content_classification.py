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
    discover_content_candidates,
    enrich_content_candidates,
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


class EmptyRecordingProvider:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def complete(self, messages: object, **kwargs: object) -> ChatCompletion:
        self.calls.append((messages, kwargs))
        return _completion(
            {
                "enterprise_profile": [],
                "products": [],
                "case_studies": [],
                "faqs": [],
                "unclassified": [],
            }
        )


@pytest.mark.asyncio
async def test_progressive_directory_is_one_compact_whole_document_call() -> None:
    provider = FakeProvider(
        _completion(
            {
                "candidates": [
                    {
                        "category": "products",
                        "label": "设备数据接入与协同",
                        "meta": {
                            "source_id": "doc-1",
                            "source_text": "核心业务：设备数据接入与协同。",
                            "confidence": 0.91,
                        },
                    }
                ]
            }
        )
    )

    discovered = await discover_content_candidates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
        max_tokens=8_192,
    )

    assert len(discovered) == 1
    assert discovered[0].label == "设备数据接入与协同"
    assert len(provider.calls) == 1
    assert provider.calls[0][1]["max_tokens"] == 4_096


@pytest.mark.asyncio
async def test_progressive_directory_accepts_provider_bare_array() -> None:
    provider = FakeProvider(
        _completion(
            json.dumps(
                [
                    {
                        "category": "products",
                        "label": "设备数据接入与协同",
                        "meta": {
                            "source_id": "doc-1",
                            "source_text": "核心业务：设备数据接入与协同。",
                            "confidence": 0.91,
                        },
                    }
                ],
                ensure_ascii=False,
            )
        )
    )

    discovered = await discover_content_candidates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
        max_tokens=4_096,
    )

    assert [item.category for item in discovered] == ["products"]


@pytest.mark.asyncio
async def test_progressive_directory_restores_pdf_compatibility_glyphs() -> None:
    document = ClassificationDocument(
        source_id="pdf-1",
        file_name="生态规划.pdf",
        content="拓浙 AI ⽣态规划书。业务包括 AI 学习培养体系。",
    )
    provider = FakeProvider(
        _completion(
            {
                "candidates": [
                    {
                        "category": "products",
                        "label": "AI 学习培养体系",
                        "meta": {
                            "source_id": "pdf-1",
                            "source_text": "拓浙 AI 生态规划书。业务包括 AI 学习培养体系。",
                            "confidence": 0.9,
                        },
                    }
                ]
            }
        )
    )

    discovered = await discover_content_candidates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
        max_tokens=4_096,
    )

    assert len(discovered) == 1
    assert discovered[0].source_text == document.content


@pytest.mark.asyncio
async def test_progressive_directory_expands_narrow_anchor_for_enrichment() -> None:
    paragraph = "AI 学习培养体系面向学生提供课程、项目实践和长期成长支持。" * 18
    document = ClassificationDocument(
        source_id="doc-long",
        file_name="规划书.txt",
        content=f"前言。\n\n{paragraph}\n\n后续规划。",
    )
    provider = FakeProvider(
        _completion(
            [
                {
                    "category": "products",
                    "label": "AI 学习培养体系",
                    "meta": {
                        "source_id": "doc-long",
                        "source_text": "AI 学习培养体系",
                        "confidence": 0.9,
                    },
                }
            ]
        )
    )

    discovered = await discover_content_candidates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
        max_tokens=4_096,
    )

    assert len(discovered[0].source_text) > 300
    assert discovered[0].source_text in document.content


@pytest.mark.asyncio
async def test_progressive_enrichment_clears_only_unsupported_field() -> None:
    directory_provider = FakeProvider(
        _completion(
            {
                "candidates": [
                    {
                        "category": "case_studies",
                        "label": "设备数据接入与协同",
                        "meta": {
                            "source_id": "doc-1",
                            "source_text": "核心业务：设备数据接入与协同。",
                            "confidence": 0.88,
                        },
                    }
                ]
            }
        )
    )
    discovered = await discover_content_candidates(
        provider=directory_provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[DOCUMENT],
        max_tokens=4_096,
    )
    provider = FakeProvider(
        _completion(
            {
                "items": [
                    {
                        "candidate_id": str(discovered[0].id),
                        "payload": {
                            "title": "设备数据接入与协同",
                            "industry": "医疗行业",
                            "client_display_name": "",
                            "background": "设备数据需要统一接入。",
                            "solution": "通过设备数据接入实现协同。",
                            "result": "形成设备数据接入与协同能力。",
                        },
                    }
                ]
            }
        )
    )

    enriched = await enrich_content_candidates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        candidates=discovered,
        max_tokens=4_096,
    )

    assert enriched[0].payload["industry"] == ""
    assert enriched[0].payload["background"]
    assert "industry" in enriched[0].field_warnings
    assert len(provider.calls) == 1


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

    assert parsed.enterprise_profile[0].meta.source_text == ("星澜智造科技有限公司位于浙江\n杭州。")


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


def test_turns_a_topic_label_into_a_natural_faq_question() -> None:
    payload = {
        **_payload(),
        "enterprise_profile": [],
        "faqs": [
            {
                "question": "设备数据接入",
                "answer": "设备数据接入与协同。",
                "meta": {
                    "source_id": "doc-1",
                    "source_text": "核心业务：设备数据接入与协同。",
                    "confidence": 0.74,
                },
            }
        ],
    }

    parsed = validate_content_classification(payload, documents=[DOCUMENT])

    assert parsed.faqs[0].question == "关于设备数据接入可以了解哪些信息？"


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
    assert result.failure_code and result.failure_code.startswith("classification_recovered:")
    assert not result.failure_code.startswith("classification_partial:")


@pytest.mark.asyncio
async def test_recovered_product_uses_verbatim_leading_subject_as_name() -> None:
    source_text = "浙客松是生态面向校内外打造的 AI 实战赛事品牌，也是人才发现的重要场景。"
    document = ClassificationDocument(
        source_id="doc-product",
        file_name="企业资料.txt",
        content=source_text,
    )
    invalid = {
        "enterprise_profile": [],
        "products": [
            {
                "name": "浙客松系列",
                "category": "赛事品牌",
                "summary": "面向校内外打造的 AI 实战赛事品牌",
                "detail": "",
                "audience": "校内外",
                "price_boundary": "",
                "meta": {
                    "source_id": "doc-product",
                    "source_text": source_text,
                    "confidence": 0.95,
                },
            }
        ],
        "case_studies": [],
        "faqs": [],
        "unclassified": [],
    }
    provider = FakeProvider(_completion(invalid), _completion(invalid))

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
    )

    assert result.status == "review"
    assert result.classification.products[0].name == "浙客松"
    assert result.failure_code and result.failure_code.startswith("classification_recovered:")


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
async def test_normal_enterprise_document_is_sent_with_full_context_once() -> None:
    provider = EmptyRecordingProvider()
    content = "企业资料开始。" + ("这里是连续的企业介绍与业务说明。" * 1_800) + "企业资料结束。"
    document = ClassificationDocument(source_id="doc-1", file_name="企业资料.txt", content=content)

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
        max_tokens=1_000,
    )

    assert result.status == "review"
    assert len(provider.calls) == 1
    user_payload = json.loads(provider.calls[0][0][1].content)
    assert user_payload["documents"][0]["content"] == content


@pytest.mark.asyncio
async def test_genuinely_long_document_uses_large_overlapping_semantic_chunks() -> None:
    provider = EmptyRecordingProvider()
    content = "企业资料开始。\n" + ("这是完整业务段落。\n" * 10_000) + "企业资料结束。"
    document = ClassificationDocument(source_id="doc-1", file_name="超长资料.txt", content=content)

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
        max_tokens=1_000,
    )

    assert result.status == "review"
    assert 1 < len(provider.calls) < 10
    chunks = [json.loads(call[0][1].content)["documents"][0]["content"] for call in provider.calls]
    assert chunks[0].startswith("企业资料开始")
    assert chunks[-1].endswith("企业资料结束。")
    assert all(len(chunk) <= 80_000 for chunk in chunks)


@pytest.mark.asyncio
async def test_duplicate_named_candidates_keep_the_more_complete_result() -> None:
    excerpt = "星澜智造科技有限公司位于浙江杭州。"
    repeated = (excerpt + "\n") * 5_000
    document = ClassificationDocument(source_id="doc-1", file_name="长资料.txt", content=repeated)
    first = _payload(source_text=excerpt)
    second = _payload(source_text=excerpt)
    second_profile = second["enterprise_profile"][0]
    assert isinstance(second_profile, dict)
    second_profile["summary"] = "位于浙江杭州"
    second_profile["meta"]["confidence"] = 0.95
    provider = FakeProvider(_completion(first), _completion(second))

    result = await classify_content_with_hard_gates(
        provider=provider,
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
        max_tokens=1_000,
    )

    assert result.status == "review"
    assert len(provider.calls) == 2
    assert len(result.classification.enterprise_profile) == 1
    assert result.classification.enterprise_profile[0].summary == "位于浙江杭州"


@pytest.mark.asyncio
async def test_repeated_truncation_creates_one_review_fallback_per_source() -> None:
    document = ClassificationDocument(
        source_id="doc-1",
        file_name="输出密集资料.txt",
        content="需要人工复核的连续资料。" * 500,
    )

    result = await classify_content_with_hard_gates(
        provider=FailingProvider(),
        credentials=ProviderCredentials(api_key="test-only"),
        documents=[document],
        max_tokens=1_000,
    )

    assert result.status == "review"
    assert len(result.classification.unclassified) == 1
    assert result.classification.unclassified[0].meta.source_id == "doc-1"


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
