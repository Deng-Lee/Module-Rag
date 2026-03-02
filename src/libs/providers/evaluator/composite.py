from __future__ import annotations

from ....core.eval.evaluator import CompositeEvaluator
from ....core.eval.metricset import MetricSet
from ....core.eval.metrics.generation import GenerationMetricSet
from .fake_judge import FakeJudge


class CompositeEvaluatorProvider(CompositeEvaluator):
    def __init__(self, k: int = 5, enable_generation: bool = True) -> None:
        metric_sets = {"retrieval": MetricSet(k=k)}
        judge = None
        if enable_generation:
            judge = FakeJudge()
            metric_sets["generation"] = GenerationMetricSet()
        super().__init__(metric_sets=metric_sets, judge=judge)
