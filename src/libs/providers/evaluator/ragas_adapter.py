from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from ...interfaces.evaluator.evaluator import EvalCaseResult


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


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
class RagasAdapter:
    """Optional adapter: delegates metric computation to RAGAS (if installed).

    Notes:
    - RAGAS internally needs an LLM/embeddings backend. We configure OpenAI-compatible
      backends via environment variables when `api_key/base_url` are provided.
    - This keeps the rest of the pipeline unchanged and avoids hard-coding an SDK.
    """

    provider_id: str = "ragas"
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    endpoint_key: str | None = None  # accepted for config compatibility (resolved upstream)

    def evaluate_case(self, case: Any, run_output: dict[str, Any]) -> EvalCaseResult:
        try:
            from ragas import evaluate  # type: ignore
            from ragas.metrics import answer_relevancy, faithfulness  # type: ignore
            from datasets import Dataset  # type: ignore
        except Exception:
            return EvalCaseResult(
                case_id=_case_id(case),
                metrics={},
                artifacts={
                    "error": "dependency_missing",
                    "dependency": "ragas",
                    "reason": "ragas_not_installed",
                },
            )
        query = _case_query(case)
        answer = run_output.get("answer") or ""
        contexts = run_output.get("retrieved_texts") or []
        if not isinstance(contexts, list):
            contexts = [str(contexts)]
        expected_answer = _case_expected_answer(case)

        payload: dict[str, Any] = {
            "question": [query],
            "answer": [answer],
            "contexts": [contexts],
        }
        if expected_answer:
            payload["ground_truth"] = [expected_answer]

        dataset = Dataset.from_dict(payload)
        env: dict[str, str] = {}
        if isinstance(self.api_key, str) and self.api_key:
            env["OPENAI_API_KEY"] = self.api_key
        if isinstance(self.base_url, str) and self.base_url:
            env["OPENAI_BASE_URL"] = self.base_url
        # Some stacks read this; harmless if ignored.
        if isinstance(self.model, str) and self.model:
            env["OPENAI_MODEL"] = self.model

        try:
            with _temp_env(env) if env else _temp_env({}):
                result = evaluate(dataset, metrics=[faithfulness, answer_relevancy])
        except Exception as exc:
            return EvalCaseResult(
                case_id=_case_id(case),
                metrics={},
                artifacts={
                    "error": "backend_error",
                    "backend": "ragas",
                    "exc_type": type(exc).__name__,
                    "message": str(exc),
                    "hint": "set OPENAI_API_KEY (or configure evaluator api_key via model_endpoints)",
                },
            )

        metrics: dict[str, float] = {}
        extracted = _extract_ragas_scores(result)
        if "faithfulness" in extracted:
            metrics["ragas.faithfulness"] = _safe_float(extracted["faithfulness"])
        if "answer_relevancy" in extracted:
            metrics["ragas.answer_relevancy"] = _safe_float(extracted["answer_relevancy"])

        return EvalCaseResult(
            case_id=_case_id(case),
            metrics=metrics,
            artifacts={"ragas_metrics": list(extracted.keys())},
        )


def _extract_ragas_scores(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return result
    if hasattr(result, "to_pandas"):
        try:
            df = result.to_pandas()
            if df is not None and len(df.index) > 0:
                row = df.iloc[0].to_dict()
                return {k: row[k] for k in row.keys()}
        except Exception:
            pass
    if hasattr(result, "dataframe"):
        try:
            df = result.dataframe
            if df is not None and len(df.index) > 0:
                row = df.iloc[0].to_dict()
                return {k: row[k] for k in row.keys()}
        except Exception:
            pass
    if hasattr(result, "scores"):
        try:
            return dict(result.scores)  # type: ignore[arg-type]
        except Exception:
            pass
    return {}


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
