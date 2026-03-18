from __future__ import annotations

from src.libs.providers.evaluator.deepeval_adapter import DeepEvalAdapter
from src.libs.providers.evaluator.ragas_adapter import RagasAdapter


def test_ragas_adapter_missing_dependency() -> None:
    adapter = RagasAdapter()
    result = adapter.evaluate_case(case={"case_id": "c1"}, run_output={})
    assert isinstance(result.artifacts, dict)
    # Dependency may be installed locally; in that case we should still fail gracefully.
    assert result.artifacts.get("error") in {"dependency_missing", "backend_error"}
    if result.artifacts.get("error") == "dependency_missing":
        assert result.artifacts.get("dependency") == "ragas"


def test_deepeval_adapter_missing_dependency() -> None:
    adapter = DeepEvalAdapter()
    result = adapter.evaluate_case(case={"case_id": "c1"}, run_output={})
    assert isinstance(result.artifacts, dict)
    assert result.artifacts.get("error") in {"dependency_missing", "backend_error"}
    if result.artifacts.get("error") == "dependency_missing":
        assert result.artifacts.get("dependency") == "deepeval"


def test_ragas_adapter_accepts_timeout_and_retry_config() -> None:
    adapter = RagasAdapter(timeout_s=12.0, max_retries=0)
    assert adapter.timeout_s == 12.0
    assert adapter.max_retries == 0
