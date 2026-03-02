from __future__ import annotations

from src.core.eval.dataset import EvalCase
from src.core.eval.metrics.generation import GenerationMetricSet
from src.libs.providers.evaluator.fake_judge import FakeJudge


def test_fake_judge_metrics() -> None:
    judge = FakeJudge()
    case = EvalCase(
        case_id="c1",
        query="What is FTS5 BM25?",
        tags=["gen"],
        expected_keywords=["FTS5"],
    )
    run_output = {
        "answer": "FTS5 uses an inverted index and BM25 scoring.",
        "context": "SQLite FTS5 builds an inverted index. BM25 ranks results.",
    }
    metrics = GenerationMetricSet().compute(case, run_output, judge)
    assert metrics["faithfulness"] > 0.0
    assert metrics["answer_relevancy"] > 0.0


def test_fake_judge_empty_answer() -> None:
    judge = FakeJudge()
    case = EvalCase(case_id="c2", query="q", tags=["gen"], expected_keywords=["k"])
    metrics = GenerationMetricSet().compute(case, {"answer": "", "context": "x"}, judge)
    assert metrics["faithfulness"] == 0.0
    assert metrics["answer_relevancy"] == 0.0
