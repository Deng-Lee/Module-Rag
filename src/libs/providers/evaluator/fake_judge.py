from __future__ import annotations

import re

from ...interfaces.evaluator.judge import JudgeScore


class FakeJudge:
    """
    Deterministic judge for offline/dev use.
    Uses token overlap to approximate faithfulness/relevancy.
    """

    provider_id = "fake"

    def score_faithfulness(self, answer: str, context: str) -> JudgeScore:
        score = _overlap_ratio(_tokens(answer), _tokens(context))
        return JudgeScore(score=score, reason="token_overlap")

    def score_answer_relevancy(self, answer: str, query: str) -> JudgeScore:
        score = _overlap_ratio(_tokens(query), _tokens(answer))
        return JudgeScore(score=score, reason="token_overlap")


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"\W+", text.lower()) if t}


def _overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / float(min(len(a), len(b)))
