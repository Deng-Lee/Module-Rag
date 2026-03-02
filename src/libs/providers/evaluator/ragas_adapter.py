from __future__ import annotations

from typing import Any

from ...interfaces.evaluator.evaluator import EvalCaseResult
from ...interfaces.evaluator.judge import JudgeScore


class RagasAdapter:
    """Optional adapter: require external ragas dependency."""

    provider_id = "evaluator.ragas"

    def evaluate_case(self, case: Any, run_output: dict[str, Any]) -> EvalCaseResult:
        try:
            import ragas  # type: ignore  # noqa: F401
        except Exception:
            return EvalCaseResult(
                case_id=getattr(case, "case_id", "unknown"),
                metrics={},
                artifacts={
                    "error": "dependency_missing",
                    "dependency": "ragas",
                    "reason": "ragas_not_installed",
                },
            )
        # TODO: map EvalCase + artifacts to ragas inputs.
        raise NotImplementedError("RAGAS adapter not wired yet")


def _as_score(value: Any) -> JudgeScore:
    try:
        return JudgeScore(score=float(value))
    except Exception:
        return JudgeScore(score=0.0, reason="invalid_score")
