from __future__ import annotations

from dataclasses import dataclass, field

from ..response import ResponseIR
from ...observability.obs import api as obs
from ...observability.trace.context import TraceContext
from .models import QueryParams, QueryRuntime
from .stages.format_response import FormatResponseStage
from .stages.query_norm import query_norm
from .stages.retrieve_dense import DenseRetrieveStage


@dataclass
class QueryPipeline:
    """Minimal online query pipeline (D-1).

    Stages:
    - stage.query_norm
    - stage.retrieve_dense
    - stage.format_response
    """

    retrieve_dense: DenseRetrieveStage = field(default_factory=DenseRetrieveStage)
    format_response: FormatResponseStage = field(default_factory=FormatResponseStage)

    def run(self, query: str, *, runtime: QueryRuntime, params: QueryParams) -> ResponseIR:
        trace_id = TraceContext.current().trace_id if TraceContext.current() else ""

        with obs.span("stage.query_norm", {"stage": "query_norm"}):
            q = query_norm(query)

        with obs.span("stage.retrieve_dense", {"stage": "retrieve_dense"}):
            candidates = self.retrieve_dense.run(q, runtime, params)

        with obs.span("stage.format_response", {"stage": "format_response"}):
            return self.format_response.run(q=q, candidates=candidates, runtime=runtime, trace_id=trace_id)
