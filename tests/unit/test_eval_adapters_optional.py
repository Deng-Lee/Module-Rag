from __future__ import annotations

from src.libs.providers.evaluator.deepeval_adapter import DeepEvalAdapter
from src.libs.providers.evaluator.ragas_adapter import RagasAdapter


def test_ragas_adapter_missing_dependency() -> None:
    adapter = RagasAdapter()
    result = adapter.evaluate_case(case={"case_id": "c1"}, run_output={})
    assert result.artifacts.get("error") == "dependency_missing"
    assert result.artifacts.get("dependency") == "ragas"


def test_deepeval_adapter_missing_dependency() -> None:
    adapter = DeepEvalAdapter()
    result = adapter.evaluate_case(case={"case_id": "c1"}, run_output={})
    assert result.artifacts.get("error") == "dependency_missing"
    assert result.artifacts.get("dependency") == "deepeval"
