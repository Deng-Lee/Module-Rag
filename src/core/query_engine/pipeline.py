from __future__ import annotations

from dataclasses import dataclass, field

from ..response import ResponseIR
from ...observability.obs import api as obs
from ...observability.trace.context import TraceContext
from .models import QueryParams, QueryRuntime
from .stages.format_response import FormatResponseStage
from .stages.fusion import FusionStage
from .stages.query_norm import query_norm
from .stages.retrieve_dense import DenseRetrieveStage
from .stages.retrieve_sparse import SparseRetrieveStage


@dataclass
class QueryPipeline:
    """Minimal online query pipeline (D-1).

    Stages:
    - stage.query_norm
    - stage.retrieve_dense
    - stage.format_response
    """

    retrieve_dense: DenseRetrieveStage = field(default_factory=DenseRetrieveStage)
    retrieve_sparse: SparseRetrieveStage = field(default_factory=SparseRetrieveStage)
    fusion: FusionStage = field(default_factory=FusionStage)
    format_response: FormatResponseStage = field(default_factory=FormatResponseStage)

    def run(self, query: str, *, runtime: QueryRuntime, params: QueryParams) -> ResponseIR:
        trace_id = TraceContext.current().trace_id if TraceContext.current() else ""

        with obs.span("stage.query_norm", {"stage": "query_norm"}):
            q = query_norm(query)

        with obs.span("stage.retrieve_dense", {"stage": "retrieve_dense"}):
            dense = self.retrieve_dense.run(q, runtime, params)
            _emit_candidates_event("dense", dense, top_k=params.top_k)

        with obs.span("stage.retrieve_sparse", {"stage": "retrieve_sparse"}):
            sparse = self.retrieve_sparse.run(q, runtime, params)
            _emit_candidates_event("sparse", sparse, top_k=params.top_k)

        candidates_by_source = {"dense": dense, "sparse": sparse}
        with obs.span("stage.fusion", {"stage": "fusion"}):
            ranked = self.fusion.run(runtime=runtime, params=params, candidates_by_source=candidates_by_source)
            _emit_ranked_event(ranked, top_k=params.top_k)

        with obs.span("stage.format_response", {"stage": "format_response"}):
            return self.format_response.run(q=q, candidates=ranked, runtime=runtime, trace_id=trace_id)


def _emit_candidates_event(source: str, candidates: list, *, top_k: int) -> None:
    # Keep the payload small; dashboard can join details from sqlite later.
    preview = [{"chunk_id": c.chunk_id, "score": float(c.score)} for c in candidates[: min(10, len(candidates))]]
    obs.event(
        "retrieval.candidates",
        {
            "source": source,
            "top_k": int(top_k),
            "count": int(len(candidates)),
            "preview": preview,
        },
    )

def _emit_ranked_event(ranked: list, *, top_k: int) -> None:
    preview = [
        {"chunk_id": r.chunk_id, "score": float(r.score), "rank": int(getattr(r, "rank", 0) or 0)}
        for r in ranked[: min(10, len(ranked))]
    ]
    obs.event(
        "retrieval.fused",
        {
            "strategy": "rrf" if ranked and getattr(ranked[0], "source", "") == "rrf" else "passthrough",
            "top_k": int(top_k),
            "count": int(len(ranked)),
            "preview": preview,
        },
    )


def _dedup_candidates(_: list) -> list:  # pragma: no cover
    # Deprecated: dedup now lives in FusionStage (D-5).
    return []
