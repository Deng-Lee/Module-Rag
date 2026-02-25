from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class EvalReport:
    run_id: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


class Evaluator(Protocol):
    def run(self, dataset_id: str, strategy_config_id: str, mode: str = "offline") -> EvalReport:
        ...
