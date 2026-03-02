from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .dataset import EvalCase
from .metricset import MetricSet
from .metrics.generation import GenerationMetricSet
from ...libs.interfaces.evaluator.evaluator import EvalCaseResult
from ...libs.interfaces.evaluator.judge import Judge


@dataclass
class CompositeEvaluator:
    metric_sets: Mapping[str, Any] = field(default_factory=dict)
    judge: Judge | None = None

    def evaluate_case(self, case: EvalCase, run_output: dict[str, Any]) -> EvalCaseResult:
        metrics: dict[str, float] = {}
        for namespace, metric_set in self.metric_sets.items():
            if isinstance(metric_set, GenerationMetricSet):
                if self.judge is None:
                    raise ValueError("judge_required_for_generation_metrics")
                computed = metric_set.compute(case, run_output, self.judge)
            elif isinstance(metric_set, MetricSet):
                computed = metric_set.compute(case, run_output)
            else:
                computed = metric_set.compute(case, run_output)  # type: ignore[call-arg]

            for key, value in computed.items():
                namespaced = f"{namespace}.{key}"
                if namespaced in metrics:
                    raise ValueError(f"metric_key_conflict:{namespaced}")
                metrics[namespaced] = float(value)

        return EvalCaseResult(case_id=case.case_id, metrics=metrics)
