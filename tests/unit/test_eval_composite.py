from __future__ import annotations

import pytest

from src.core.eval.dataset import EvalCase
from src.core.eval.evaluator import CompositeEvaluator
from src.core.eval.metricset import MetricSet
from src.core.eval.metrics.generation import GenerationMetricSet
from src.libs.providers.evaluator.fake_judge import FakeJudge


def test_composite_evaluator_merges_metrics() -> None:
    evaluator = CompositeEvaluator(
        metric_sets={
            "retrieval": MetricSet(k=3),
            "generation": GenerationMetricSet(),
        },
        judge=FakeJudge(),
    )
    case = EvalCase(
        case_id="c1",
        query="What is RRF?",
        tags=["retrieval", "gen"],
        expected_chunk_ids=["c2"],
    )
    run_output = {
        "ranked_chunk_ids": ["c1", "c2"],
        "answer": "RRF is reciprocal rank fusion.",
        "context": "RRF merges rankings from multiple retrievers.",
    }
    result = evaluator.evaluate_case(case, run_output)
    assert "retrieval.hit_rate@3" in result.metrics
    assert "retrieval.mrr" in result.metrics
    assert "generation.faithfulness" in result.metrics
    assert "generation.answer_relevancy" in result.metrics


def test_generation_requires_judge() -> None:
    evaluator = CompositeEvaluator(metric_sets={"generation": GenerationMetricSet()}, judge=None)
    case = EvalCase(
        case_id="c1",
        query="q",
        tags=["gen"],
        expected_keywords=["k"],
    )
    with pytest.raises(ValueError, match="judge_required"):
        evaluator.evaluate_case(case, {"answer": "a", "context": "c"})
