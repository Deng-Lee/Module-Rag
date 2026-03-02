from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class JudgeScore:
    score: float
    reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class Judge(Protocol):
    provider_id: str

    def score_faithfulness(self, answer: str, context: str) -> JudgeScore:
        ...

    def score_answer_relevancy(self, answer: str, query: str) -> JudgeScore:
        ...
