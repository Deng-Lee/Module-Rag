from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from ...interfaces.evaluator.evaluator import EvalCaseResult


@contextmanager
def _temp_env(pairs: dict[str, str]) -> Any:
    prev: dict[str, str | None] = {k: os.environ.get(k) for k in pairs}
    try:
        for k, v in pairs.items():
            os.environ[k] = v
        yield
    finally:
        for k, old in prev.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


@dataclass
class DeepEvalAdapter:
    """Optional adapter: delegates metric computation to DeepEval (if installed)."""

    provider_id: str = "deepeval"
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    endpoint_key: str | None = None  # accepted for config compatibility (resolved upstream)

    def evaluate_case(self, case: Any, run_output: dict[str, Any]) -> EvalCaseResult:
        try:
            from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric  # type: ignore
            from deepeval.test_case import LLMTestCase  # type: ignore
        except Exception:
            return EvalCaseResult(
                case_id=_case_id(case),
                metrics={},
                artifacts={
                    "error": "dependency_missing",
                    "dependency": "deepeval",
                    "reason": "deepeval_not_installed",
                },
            )
        query = _case_query(case)
        answer = run_output.get("answer") or ""
        contexts = run_output.get("retrieved_texts") or []
        if not isinstance(contexts, list):
            contexts = [str(contexts)]
        expected_answer = _case_expected_answer(case)

        test_case = LLMTestCase(
            input=query,
            actual_output=answer,
            expected_output=expected_answer,
            retrieval_context=contexts,
        )

        metrics: dict[str, float] = {}
        artifacts: dict[str, Any] = {}

        env: dict[str, str] = {}
        if isinstance(self.api_key, str) and self.api_key:
            env["OPENAI_API_KEY"] = self.api_key
        if isinstance(self.base_url, str) and self.base_url:
            env["OPENAI_BASE_URL"] = self.base_url
        if isinstance(self.model, str) and self.model:
            env["OPENAI_MODEL"] = self.model

        with _temp_env(env) if env else _temp_env({}):
            try:
                faith = FaithfulnessMetric()
                faith.measure(test_case)
                metrics["deepeval.faithfulness"] = float(faith.score or 0.0)
            except Exception as exc:
                artifacts["faithfulness_error"] = str(exc)

            try:
                rel = AnswerRelevancyMetric()
                rel.measure(test_case)
                metrics["deepeval.answer_relevancy"] = float(rel.score or 0.0)
            except Exception as exc:
                artifacts["answer_relevancy_error"] = str(exc)

        return EvalCaseResult(
            case_id=_case_id(case),
            metrics=metrics,
            artifacts=artifacts
            if metrics
            else {
                **artifacts,
                "error": "backend_error",
                "backend": "deepeval",
                "hint": "set OPENAI_API_KEY (or configure evaluator api_key via model_endpoints)",
            },
        )


def _case_id(case: Any) -> str:
    if isinstance(case, dict):
        return str(case.get("case_id") or "unknown")
    return str(getattr(case, "case_id", "unknown"))


def _case_query(case: Any) -> str:
    if isinstance(case, dict):
        return str(case.get("query") or "")
    return str(getattr(case, "query", "") or "")


def _case_expected_answer(case: Any) -> str | None:
    if isinstance(case, dict):
        value = case.get("expected_answer")
    else:
        value = getattr(case, "expected_answer", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None
