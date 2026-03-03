from __future__ import annotations

from ....core.eval.evaluator import CompositeEvaluator
from ....core.eval.metricset import MetricSet
from ....core.eval.metrics.generation import GenerationMetricSet


class CompositeEvaluatorProvider(CompositeEvaluator):
    def __init__(self, k: int = 5, enable_generation: bool = False) -> None:
        metric_sets = {"retrieval": MetricSet(k=k)}
        judge = None
        if enable_generation:
            # This provider cannot construct a Judge by itself (no access to registry).
            # Use EvalRunner's config-driven composite evaluator if you need generation metrics.
            raise ValueError("enable_generation_requires_external_judge")
            metric_sets["generation"] = GenerationMetricSet()
        super().__init__(metric_sets=metric_sets, judge=judge)
