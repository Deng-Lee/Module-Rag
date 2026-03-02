from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class _EvalRunLike(Protocol):
    dataset_id: str
    strategy_config_id: str
    metrics: Mapping[str, float]
    cases: list[Any]


@dataclass(frozen=True)
class GateFailure:
    key: str
    value: float | None
    threshold: float


def assert_metrics_ge(metrics: Mapping[str, float], thresholds: Mapping[str, float]) -> list[GateFailure]:
    failures: list[GateFailure] = []
    for key, threshold in thresholds.items():
        value = metrics.get(key)
        if value is None or float(value) < float(threshold):
            failures.append(GateFailure(key=key, value=value, threshold=float(threshold)))
    return failures


def format_failure_report(run: _EvalRunLike, thresholds: Mapping[str, float]) -> str:
    failures = assert_metrics_ge(run.metrics, thresholds)
    if not failures:
        return "quality_gate_passed"

    lines: list[str] = []
    lines.append("QUALITY GATE FAILED")
    lines.append(f"strategy_config_id: {run.strategy_config_id}")
    lines.append(f"dataset_id: {run.dataset_id}")
    lines.append("")
    lines.append("Aggregate metrics:")
    for f in failures:
        lines.append(f"- {f.key}: {f.value} < {f.threshold}")

    # Case-level hints: show traces for the lowest scoring cases per failing key.
    lines.append("")
    lines.append("Case diagnostics (lowest scores):")
    for f in failures:
        key = f.key
        cases = sorted(run.cases, key=lambda c: c.metrics.get(key, 0.0))[:3]
        for c in cases:
            lines.append(
                f"- {key} case_id={c.case_id} trace_id={c.trace_id} value={c.metrics.get(key)}"
            )
    return "\n".join(lines)
