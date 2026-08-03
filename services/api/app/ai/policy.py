"""Deterministic input safety, evidence gating, and quotation controls."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Sequence

from .schemas import ChatMessage, Refusal, RefusalCode, RetrievedEvidence, StructuredModelAnswer


class PolicyFlag(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    SENSITIVE_DATA = "sensitive_data"
    HIGH_RISK = "high_risk"
    PRICING = "pricing"
    MONETIZATION = "monetization"


class QuestionScope(StrEnum):
    """Server-owned interpretation of what kind of answer the user requested."""

    ENTERPRISE = "enterprise"
    GENERAL = "general"
    AMBIGUOUS = "ambiguous"
    MIXED = "mixed"
    # The wording does not prove whether the subject is the current enterprise
    # or an open-domain topic.  The orchestrator must probe published knowledge
    # before resolving this to ENTERPRISE or GENERAL.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class InputPolicyDecision:
    normalized_text: str
    flags: tuple[PolicyFlag, ...]
    refusal: Refusal | None = None

    @property
    def blocked(self) -> bool:
        return self.refusal is not None


@dataclass(frozen=True, slots=True)
class InputSecurityConfig:
    max_chars: int = 4000

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")


_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|prompts)",
        r"(?:reveal|show|print|repeat|dump).{0,50}(?:system|developer)\s+(?:prompt|message|instructions)",
        r"(?:act\s+as|enable)\s+(?:dan|developer\s+mode|jailbreak)",
        r"忽略.{0,20}(?:之前|以上|先前).{0,20}(?:指令|规则|提示词)",
        r"(?:显示|输出|复述|泄露|告诉我).{0,40}(?:系统提示词|开发者指令|隐藏指令)",
        r"(?:越狱|开发者模式|无视安全规则)",
    )
)

_SENSITIVE_DATA_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        r"\bBearer\s+[A-Za-z0-9._~+/-]{12,}=*",
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"(?:api[_ -]?key|访问密钥|私钥|密码).{0,15}(?:是|:|=)\s*\S{8,}",
    )
)

_HIGH_RISK_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:保证|承诺).{0,12}(?:收益|回报|效果|通过|成交)",
        r"(?:保本|稳赚|零风险|最终法律意见|代签合同)",
        r"(?:诊断|处方|用药剂量|停药建议)",
        r"(?:guaranteed return|risk[- ]free|medical diagnosis|legal conclusion)",
    )
)

_PRICING_PATTERN = re.compile(
    r"(?:报价|价格|多少钱|费用|收费|折扣|优惠|套餐|price|pricing|quote|cost|discount)",
    re.IGNORECASE,
)

_PRICING_EVIDENCE_PATTERN = re.compile(
    r"(?:[¥￥$]\s*\d|(?:USD|CNY|RMB)\s*\d|\d[\d,.]*\s*(?:元|万元|人民币|美元|/月|/年|每月|每年)|报价|价格|套餐)",
    re.IGNORECASE,
)

_MONETIZATION_PATTERN = re.compile(
    r"(?:商业模式|盈利模式|怎么(?:赚|挣)钱|如何(?:赚|挣)钱|盈利|营收|收入来源|变现)",
    re.IGNORECASE,
)

_MONETIZATION_EVIDENCE_PATTERN = re.compile(
    r"(?:商业模式|盈利模式|收入来源|营收|收费模式|按项目收费|项目收费|服务费|"
    r"订阅费|会员费|佣金|赞助收入|变现)",
    re.IGNORECASE,
)

_MONEY_CLAIM_PATTERN = re.compile(
    r"(?:[¥￥$]\s*\d[\d,]*(?:\.\d+)?(?:\s*/(?:月|年))?"
    r"|(?:USD|CNY|RMB)\s*\d[\d,]*(?:\.\d+)?(?:\s*/(?:month|year))?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:万元|元|人民币|美元)(?:\s*/(?:月|年))?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:每月|每年))",
    re.IGNORECASE,
)

_GREETING_OR_ACK_PATTERN = re.compile(
    r"^\s*(?:你好|您好|嗨|hi|hello|谢谢|感谢|好的|好呀|明白了|知道了|再见)[！!。.]?\s*$",
    re.IGNORECASE,
)

_ENTERPRISE_REFERENCE_PATTERN = re.compile(
    r"(?:贵司|你们(?:公司|企业|团队)?|你司|"
    r"(?:这家|这间|该|当前|本)(?:公司|企业|集团|团队|机构|品牌))",
    re.IGNORECASE,
)

_ENTERPRISE_TOPIC_PATTERN = re.compile(
    r"(?:公司|企业|集团|团队|品牌|创始人|负责人|员工|成员|业务|产品|服务|"
    r"案例|客户|资质|荣誉|标准版|专业版|基础版|套餐|方案|报价|价格|收费|"
    r"合作|加入|应聘|招聘|商业模式|"
    r"盈利|营收|收入|赚钱|挣钱|变现|架构|技术栈|技术方案|数据安全|联系方式|地址|办公地点|"
    r"成立|发展历程|愿景|使命|做什么|做哪些)",
    re.IGNORECASE,
)

_EXPLICIT_GENERAL_SCOPE_PATTERN = re.compile(
    r"(?:一般来说|通常来说|通用(?:知识|问题|做法|建议)?|问个(?:别的|通用)问题|"
    r"不针对(?:这家|当前)?(?:公司|企业)|不谈(?:公司|企业)|纯技术|经典模式)",
    re.IGNORECASE,
)

_GENERAL_TASK_PATTERN = re.compile(
    r"(?:翻译|改写|润色|校对|写(?:一句|一段|一封|一份|个)|文案|代码|编程|算法|"
    r"数学|天气|会议纪要|学习方法|生活建议|旅行|菜谱|头脑风暴|行动建议|"
    r"整理|排版|总结|介绍|什么是|解释(?:一下)?|帮我想)",
    re.IGNORECASE,
)

_CONTEXTUAL_FOLLOW_UP_PATTERN = re.compile(
    r"^(?:[?？]+|(?:那|那么|然后|还有|再|继续|为什么|怎么|具体|上面|前面|"
    r"这个|那个|它|他们|这些|那些).{0,18})[?？!！。.]?$",
    re.IGNORECASE,
)

_ASSISTANT_META_OR_CASUAL_PATTERN = re.compile(
    r"(?:你是谁|你是(?:人|机器人|AI)吗|你会什么|能聊什么|讲个笑话|"
    r"陪我聊|随便聊|你有病|无聊|心情|晚安)",
    re.IGNORECASE,
)

_POSSIBLE_NAMED_SUBJECT_PATTERN = re.compile(
    r"^(?:(?:请)?(?:介绍|说说|讲讲|了解|解释|总结|分析)(?:一下)?[\s:：]*"
    r"[^，。！？?]{2,48}|什么是[^，。！？?]{2,48}|[^，。！？?]{2,48}"
    r"(?:是什么|是做什么的|怎么样|如何参与|怎么参与|怎么报名))[？?。.]?$",
    re.IGNORECASE,
)


def classify_question_scope(
    text: str,
    history: Sequence[ChatMessage] = (),
) -> QuestionScope:
    """Classify conservatively for an enterprise-card assistant.

    Explicit general requests remain available, while enterprise topics and
    enterprise-context follow-ups stay inside the published-evidence boundary.
    Unknown first-turn subjects remain unresolved so the orchestrator can
    probe enterprise knowledge before allowing an open-domain answer.
    """

    normalized = _normalize_input(text)
    current = _classify_scope_without_history(normalized)
    if current is not QuestionScope.AMBIGUOUS:
        return current

    for message in reversed(history):
        if message.role != "user" or not message.content.strip():
            continue
        previous = _classify_scope_without_history(_normalize_input(message.content))
        if previous in {QuestionScope.ENTERPRISE, QuestionScope.MIXED}:
            return QuestionScope.ENTERPRISE
        if previous is QuestionScope.GENERAL:
            return QuestionScope.GENERAL
    return QuestionScope.AMBIGUOUS


def _classify_scope_without_history(text: str) -> QuestionScope:
    if _GREETING_OR_ACK_PATTERN.fullmatch(text):
        return QuestionScope.GENERAL

    has_reference = bool(_ENTERPRISE_REFERENCE_PATTERN.search(text))
    has_enterprise_topic = bool(_ENTERPRISE_TOPIC_PATTERN.search(text))
    has_explicit_general_scope = bool(_EXPLICIT_GENERAL_SCOPE_PATTERN.search(text))
    has_general_task = bool(_GENERAL_TASK_PATTERN.search(text))

    if has_reference and (has_explicit_general_scope or has_general_task):
        return QuestionScope.MIXED
    if has_reference:
        return QuestionScope.ENTERPRISE
    if has_explicit_general_scope:
        return QuestionScope.GENERAL
    if has_enterprise_topic:
        return QuestionScope.ENTERPRISE
    if _ASSISTANT_META_OR_CASUAL_PATTERN.search(text):
        return QuestionScope.GENERAL
    if _POSSIBLE_NAMED_SUBJECT_PATTERN.fullmatch(text):
        return QuestionScope.UNRESOLVED
    if has_general_task:
        return QuestionScope.GENERAL
    if _CONTEXTUAL_FOLLOW_UP_PATTERN.fullmatch(text):
        return QuestionScope.AMBIGUOUS
    return QuestionScope.UNRESOLVED


class InputSecurityPolicy:
    def __init__(self, config: InputSecurityConfig | None = None) -> None:
        self.config = config or InputSecurityConfig()

    def evaluate(self, text: str) -> InputPolicyDecision:
        normalized = _normalize_input(text)
        if not normalized:
            return InputPolicyDecision(
                normalized_text="",
                flags=(),
                refusal=Refusal(
                    code=RefusalCode.INPUT_INVALID,
                    reason="问题不能为空。",
                    safe_alternative="请重新输入一个具体问题。",
                ),
            )
        if len(normalized) > self.config.max_chars:
            return InputPolicyDecision(
                normalized_text="",
                flags=(),
                refusal=Refusal(
                    code=RefusalCode.INPUT_INVALID,
                    reason="问题长度超过允许范围。",
                    safe_alternative="请缩短问题后重试。",
                ),
            )

        flags: list[PolicyFlag] = []
        if any(pattern.search(normalized) for pattern in _SENSITIVE_DATA_PATTERNS):
            flags.append(PolicyFlag.SENSITIVE_DATA)
            return InputPolicyDecision(
                normalized_text="",
                flags=tuple(flags),
                refusal=Refusal(
                    code=RefusalCode.SENSITIVE_DATA_REQUEST,
                    reason="请勿在问答中提交密钥、密码或私钥等敏感凭据。",
                    safe_alternative="请删除敏感值后重新描述需求。",
                ),
            )
        if any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS):
            flags.append(PolicyFlag.PROMPT_INJECTION)
            return InputPolicyDecision(
                normalized_text="",
                flags=tuple(flags),
                refusal=Refusal(
                    code=RefusalCode.PROMPT_INJECTION,
                    reason="该请求试图改变系统规则或获取隐藏指令，无法处理。",
                    safe_alternative="可以直接询问已发布的企业、产品或服务信息。",
                ),
            )
        if any(pattern.search(normalized) for pattern in _HIGH_RISK_PATTERNS):
            flags.append(PolicyFlag.HIGH_RISK)
        if _PRICING_PATTERN.search(normalized):
            flags.append(PolicyFlag.PRICING)
        if _MONETIZATION_PATTERN.search(normalized):
            flags.append(PolicyFlag.MONETIZATION)
        return InputPolicyDecision(normalized_text=normalized, flags=tuple(flags))


@dataclass(frozen=True, slots=True)
class EvidenceGateConfig:
    min_score: float = 0.0
    min_vector_score: float | None = None
    min_lexical_score: float | None = None
    max_evidence: int = 8
    high_risk_min_evidence: int = 2
    allow_general_answers_without_evidence: bool = False

    def __post_init__(self) -> None:
        if self.max_evidence <= 0 or self.high_risk_min_evidence <= 0:
            raise ValueError("evidence limits must be positive")
        if self.min_vector_score is not None and not -1 <= self.min_vector_score <= 1:
            raise ValueError("min_vector_score must be between -1 and 1")
        if self.min_lexical_score is not None and not 0 <= self.min_lexical_score <= 1:
            raise ValueError("min_lexical_score must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class EvidenceGateDecision:
    evidence: tuple[RetrievedEvidence, ...]
    refusal: Refusal | None
    needs_human_review: bool = False
    general_answer_allowed: bool = False

    @property
    def allowed(self) -> bool:
        return self.refusal is None


@dataclass(frozen=True, slots=True)
class OutputGateDecision:
    evidence: tuple[RetrievedEvidence, ...]
    refusal: Refusal | None
    needs_human_review: bool = False

    @property
    def allowed(self) -> bool:
        return self.refusal is None


class EvidenceGate:
    """Require published evidence before generation and validate claims after it."""

    def __init__(self, config: EvidenceGateConfig | None = None) -> None:
        self.config = config or EvidenceGateConfig()

    def before_generation(
        self,
        decision: InputPolicyDecision,
        evidence: Sequence[RetrievedEvidence],
        *,
        question_scope: QuestionScope = QuestionScope.ENTERPRISE,
    ) -> EvidenceGateDecision:
        accepted = self.accepted_evidence(evidence)
        flags = set(decision.flags)
        if not accepted:
            if self.allows_evidence_free_answer(
                decision,
                question_scope=question_scope,
            ):
                return EvidenceGateDecision(
                    evidence=(),
                    refusal=None,
                    general_answer_allowed=True,
                )
            return EvidenceGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.INSUFFICIENT_EVIDENCE,
                    reason="当前已发布资料未说明这个企业信息，我不能补充或推测。",
                    safe_alternative="你可以换个更具体的问法，或联系企业工作人员确认。",
                ),
            )

        if PolicyFlag.PRICING in flags and not any(
            _has_pricing_evidence(item) for item in accepted
        ):
            return EvidenceGateDecision(
                evidence=accepted,
                refusal=Refusal(
                    code=RefusalCode.UNVERIFIED_PRICING,
                    reason="已发布资料中没有可核验的报价信息。",
                    safe_alternative="请联系企业工作人员获取正式报价。",
                ),
                needs_human_review=True,
            )

        if (
            question_scope is QuestionScope.ENTERPRISE
            and PolicyFlag.MONETIZATION in flags
            and not any(_has_monetization_evidence(item) for item in accepted)
        ):
            return EvidenceGateDecision(
                evidence=accepted,
                refusal=Refusal(
                    code=RefusalCode.INSUFFICIENT_EVIDENCE,
                    reason="当前已发布资料没有说明企业的盈利或收入模式，我不能据此推测。",
                    safe_alternative="如需确认，请联系企业工作人员了解正式商业模式。",
                ),
                needs_human_review=True,
            )

        authoritative = any(bool(item.metadata.get("authoritative")) for item in accepted)
        if (
            PolicyFlag.HIGH_RISK in flags
            and len(accepted) < self.config.high_risk_min_evidence
            and not authoritative
        ):
            return EvidenceGateDecision(
                evidence=accepted,
                refusal=Refusal(
                    code=RefusalCode.HIGH_RISK_UNSUPPORTED,
                    reason="该高风险问题缺少足够的权威资料支持。",
                    safe_alternative="请转交具备授权的工作人员复核。",
                ),
                needs_human_review=True,
            )
        return EvidenceGateDecision(
            evidence=accepted,
            refusal=None,
            needs_human_review=PolicyFlag.HIGH_RISK in flags,
            general_answer_allowed=(
                self.allows_general_answer(decision, question_scope=question_scope)
            ),
        )

    def accepted_evidence(
        self,
        evidence: Sequence[RetrievedEvidence],
    ) -> tuple[RetrievedEvidence, ...]:
        """Return the exact calibrated evidence set used by the policy gate.

        Query planning uses this method to measure per-subquery coverage with
        the same thresholds that later control generation.  Keeping one source
        of truth prevents a weak retrieval candidate from being counted as a
        covered long-tail question.
        """

        return tuple(
            item
            for item in sorted(evidence, key=lambda item: item.score, reverse=True)
            if self._score_allowed(item) and item.text.strip()
        )[: self.config.max_evidence]

    def allows_general_answer(
        self,
        decision: InputPolicyDecision,
        *,
        question_scope: QuestionScope = QuestionScope.ENTERPRISE,
    ) -> bool:
        flags = set(decision.flags)
        return (
            self.config.allow_general_answers_without_evidence
            and question_scope is QuestionScope.GENERAL
            and PolicyFlag.PRICING not in flags
            and PolicyFlag.HIGH_RISK not in flags
        )

    def allows_evidence_free_answer(
        self,
        decision: InputPolicyDecision,
        *,
        question_scope: QuestionScope = QuestionScope.ENTERPRISE,
    ) -> bool:
        """Allow open-domain answers without weakening enterprise grounding.

        General questions may be answered from the model's own knowledge. A
        mixed request may still answer its clearly separated general portion.
        Pure enterprise requests must have accepted published evidence before
        the model is called, so a helpful tone can never turn into invented
        company facts.
        """

        return (
            self.config.allow_general_answers_without_evidence
            and question_scope
            in {
                QuestionScope.GENERAL,
                QuestionScope.MIXED,
            }
            and PolicyFlag.HIGH_RISK not in set(decision.flags)
        )

    def _score_allowed(self, item: RetrievedEvidence) -> bool:
        if item.score < self.config.min_score:
            return False
        configured_threshold = False
        threshold_passed = False
        if self.config.min_vector_score is not None and item.vector_score is not None:
            configured_threshold = True
            threshold_passed = threshold_passed or item.vector_score >= self.config.min_vector_score
        if self.config.min_lexical_score is not None and item.lexical_score is not None:
            configured_threshold = True
            threshold_passed = (
                threshold_passed or item.lexical_score >= self.config.min_lexical_score
            )
        return threshold_passed if configured_threshold else True

    def after_generation(
        self,
        decision: InputPolicyDecision,
        output: StructuredModelAnswer,
        evidence: Sequence[RetrievedEvidence],
        *,
        question_scope: QuestionScope = QuestionScope.ENTERPRISE,
    ) -> OutputGateDecision:
        if output.refusal_reason:
            return OutputGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.MODEL_REFUSAL,
                    reason=output.refusal_reason,
                    safe_alternative="请补充问题细节或联系企业工作人员。",
                ),
                needs_human_review=output.needs_human_review,
            )

        flags = set(decision.flags)
        by_id = {item.evidence_id: item for item in evidence}
        requested = tuple(output.cited_evidence_ids)
        if not requested:
            if (
                not evidence
                and PolicyFlag.PRICING in flags
                and _unsupported_money_claims(output.answer, ())
            ):
                return OutputGateDecision(
                    evidence=(),
                    refusal=Refusal(
                        code=RefusalCode.UNVERIFIED_PRICING,
                        reason="回答包含未核验的金额，已阻止输出。",
                        safe_alternative="请联系企业工作人员获取正式报价。",
                    ),
                    needs_human_review=True,
                )
            if not evidence and self.allows_evidence_free_answer(
                decision,
                question_scope=question_scope,
            ):
                unsupported = _unsupported_money_claims(output.answer, ())
                if PolicyFlag.PRICING not in flags or not unsupported:
                    return OutputGateDecision(evidence=(), refusal=None)
                return OutputGateDecision(
                    evidence=(),
                    refusal=Refusal(
                        code=RefusalCode.UNVERIFIED_PRICING,
                        reason="回答包含未核验的金额，已阻止输出。",
                        safe_alternative="可以说明需求范围，我会先帮你整理询价要点。",
                    ),
                    needs_human_review=True,
                )
            if self.allows_general_answer(decision, question_scope=question_scope):
                return OutputGateDecision(evidence=(), refusal=None)
            return OutputGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.UNGROUNDED_OUTPUT,
                    reason="模型回答未能通过来源一致性校验。",
                    safe_alternative="请稍后重试或联系企业工作人员。",
                ),
                needs_human_review=True,
            )
        if any(evidence_id not in by_id for evidence_id in requested):
            if not evidence and self.allows_evidence_free_answer(
                decision,
                question_scope=question_scope,
            ):
                unsupported = _unsupported_money_claims(output.answer, ())
                if PolicyFlag.PRICING in flags and unsupported:
                    return OutputGateDecision(
                        evidence=(),
                        refusal=Refusal(
                            code=RefusalCode.UNVERIFIED_PRICING,
                            reason="回答包含未核验的金额，已阻止输出。",
                            safe_alternative="可以说明需求范围，我会先帮你整理询价要点。",
                        ),
                        needs_human_review=True,
                    )
                # An invented optional citation must not hide an otherwise
                # useful evidence-free answer. No unverified id is retained.
                return OutputGateDecision(
                    evidence=(),
                    refusal=None,
                )
            if self.allows_general_answer(decision, question_scope=question_scope):
                # Ordinary chat may carry an optional model citation. Keep
                # only ids that the server actually supplied.
                return OutputGateDecision(
                    evidence=tuple(
                        by_id[evidence_id]
                        for evidence_id in requested
                        if evidence_id in by_id
                    ),
                    refusal=None,
                )
            return OutputGateDecision(
                evidence=(),
                refusal=Refusal(
                    code=RefusalCode.UNGROUNDED_OUTPUT,
                    reason="模型回答未能通过来源一致性校验。",
                    safe_alternative="请稍后重试或联系企业工作人员。",
                ),
                needs_human_review=True,
            )
        cited = tuple(by_id[evidence_id] for evidence_id in requested)

        if PolicyFlag.PRICING in flags:
            unsupported = _unsupported_money_claims(output.answer, cited)
            if unsupported:
                return OutputGateDecision(
                    evidence=cited,
                    refusal=Refusal(
                        code=RefusalCode.UNVERIFIED_PRICING,
                        reason="回答包含未在引用资料中核验的金额，已阻止输出。",
                        safe_alternative="请联系企业工作人员获取正式报价。",
                    ),
                    needs_human_review=True,
                )

        return OutputGateDecision(
            evidence=cited,
            refusal=None,
            needs_human_review=(
                output.needs_human_review or PolicyFlag.HIGH_RISK in flags
            ),
        )


def _normalize_input(text: str) -> str:
    if not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    normalized = "".join(
        character
        for character in normalized
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
    )
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _has_pricing_evidence(evidence: RetrievedEvidence) -> bool:
    if str(evidence.metadata.get("content_type", "")).lower() in {
        "pricing",
        "price_list",
        "quotation",
        "offer",
    }:
        return True
    return bool(_PRICING_EVIDENCE_PATTERN.search(evidence.text))


def _has_monetization_evidence(evidence: RetrievedEvidence) -> bool:
    return bool(_MONETIZATION_EVIDENCE_PATTERN.search(evidence.text))


def _unsupported_money_claims(
    answer: str,
    evidence: Sequence[RetrievedEvidence],
) -> tuple[str, ...]:
    claims = tuple(dict.fromkeys(match.group(0) for match in _MONEY_CLAIM_PATTERN.finditer(answer)))
    if not claims:
        return ()
    source = _compact("\n".join(item.text for item in evidence))
    return tuple(claim for claim in claims if _compact(claim) not in source)


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()
