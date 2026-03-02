from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..dataset import EvalCase
from ....libs.interfaces.evaluator.judge import Judge


@dataclass
class GenerationMetricSet:
    def compute(self, case: EvalCase, run_output: dict[str, Any], judge: Judge) -> dict[str, float]:
        answer = _coalesce(run_output, ["answer", "answer_markdown", "response", "text"])
        context = _coalesce(run_output, ["context", "context_text", "context_markdown"])
        faith = judge.score_faithfulness(answer, context).score
        rel = judge.score_answer_relevancy(answer, case.query).score
        return {
            "faithfulness": float(faith),
            "answer_relevancy": float(rel),
        }


def _coalesce(run_output: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = run_output.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""
