from __future__ import annotations

from src.core.eval.dataset import EvalCase
from src.core.eval.metricset import MetricSet
from src.core.eval.metrics.retrieval import hit_rate_at_k, mrr, ndcg_at_k


def test_retrieval_metrics_basic() -> None:
    ranked = ["c1", "c2", "c3", "c4"]
    expected = ["c3"]
    assert hit_rate_at_k(ranked, expected, 3) == 1.0
    assert mrr(ranked, expected) == 1.0 / 3.0
    assert ndcg_at_k(ranked, expected, 3) == 0.5


def test_retrieval_metrics_empty() -> None:
    ranked: list[str] = []
    expected: list[str] = []
    assert hit_rate_at_k(ranked, expected, 5) == 0.0
    assert mrr(ranked, expected) == 0.0
    assert ndcg_at_k(ranked, expected, 5) == 0.0


def test_metricset_compute() -> None:
    case = EvalCase(
        case_id="c1",
        query="q",
        tags=["retrieval"],
        expected_chunk_ids=["c2"],
    )
    metrics = MetricSet(k=3).compute(case, {"ranked_chunk_ids": ["c1", "c2", "c3"]})
    assert metrics["hit_rate@3"] == 1.0
    assert metrics["mrr"] == 1.0 / 2.0
    assert metrics["ndcg@3"] > 0
