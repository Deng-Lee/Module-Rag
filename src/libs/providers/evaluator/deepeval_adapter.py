from __future__ import annotations

from typing import Any

from ...interfaces.evaluator.evaluator import EvalCaseResult


class DeepEvalAdapter:
    """Optional adapter: require external deepeval dependency."""

    provider_id = "evaluator.deepeval"

    def evaluate_case(self, case: Any, run_output: dict[str, Any]) -> EvalCaseResult:
        try:
            import deepeval  # type: ignore  # noqa: F401
        except Exception:
            return EvalCaseResult(
                case_id=getattr(case, "case_id", "unknown"),
                metrics={},
                artifacts={
                    "error": "dependency_missing",
                    "dependency": "deepeval",
                    "reason": "deepeval_not_installed",
                },
            )
        # TODO: map EvalCase + artifacts to deepeval inputs.
        raise NotImplementedError("DeepEval adapter not wired yet")
