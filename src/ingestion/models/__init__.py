from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..errors import IngestionError
from ...observability.trace.envelope import TraceEnvelope


@dataclass
class StageContext:
    strategy_config_id: str
    trace_id: str
    stage: str


ProgressCallback = Callable[[str, float, str, dict[str, Any] | None], None]


@dataclass
class IngestResult:
    trace_id: str
    status: str
    output: Any | None = None
    error: IngestionError | None = None
    trace: TraceEnvelope | None = None
