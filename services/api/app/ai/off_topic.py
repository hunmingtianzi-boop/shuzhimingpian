"""Enterprise-owned policy for bounded off-topic chat."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

OFF_TOPIC_POLICY_SETTINGS_KEY = "ai_assistant_policy"
DEFAULT_OFF_TOPIC_QUESTION_LIMIT = 3
MIN_OFF_TOPIC_QUESTION_LIMIT = 1
MAX_OFF_TOPIC_QUESTION_LIMIT = 10


class OffTopicAnswerMode(StrEnum):
    BLOCKED = "blocked"
    LIMITED = "limited"
    UNLIMITED = "unlimited"


@dataclass(frozen=True, slots=True)
class OffTopicPolicy:
    answer_mode: OffTopicAnswerMode = OffTopicAnswerMode.LIMITED
    question_limit: int = DEFAULT_OFF_TOPIC_QUESTION_LIMIT

    @classmethod
    def from_company_settings(cls, settings: Mapping[str, Any]) -> "OffTopicPolicy":
        raw_policy = settings.get(OFF_TOPIC_POLICY_SETTINGS_KEY)
        if not isinstance(raw_policy, Mapping):
            return cls()
        raw_mode = raw_policy.get("off_topic_answer_mode")
        try:
            answer_mode = OffTopicAnswerMode(raw_mode)
        except (TypeError, ValueError):
            # Read the first implementation's boolean switch so existing
            # company settings upgrade without changing their behavior.
            answer_mode = (
                OffTopicAnswerMode.BLOCKED
                if raw_policy.get("allow_off_topic_questions", True) is not True
                else OffTopicAnswerMode.LIMITED
            )
        raw_limit = raw_policy.get(
            "off_topic_question_limit", DEFAULT_OFF_TOPIC_QUESTION_LIMIT
        )
        question_limit = (
            raw_limit
            if isinstance(raw_limit, int) and not isinstance(raw_limit, bool)
            else DEFAULT_OFF_TOPIC_QUESTION_LIMIT
        )
        return cls(
            answer_mode=answer_mode,
            question_limit=max(
                MIN_OFF_TOPIC_QUESTION_LIMIT,
                min(question_limit, MAX_OFF_TOPIC_QUESTION_LIMIT),
            ),
        )

    def as_company_setting(self) -> dict[str, str | int]:
        return {
            "off_topic_answer_mode": self.answer_mode.value,
            "off_topic_question_limit": self.question_limit,
        }
