from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..response import ResponseIR
from ...observability.obs import api as obs
from ...observability.trace.context import TraceContext
from .models import QueryParams, QueryRuntime
from .stages.format_response import FormatResponseStage
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

        candidates = _dedup_candidates(dense + sparse)

        with obs.span("stage.format_response", {"stage": "format_response"}):
            return self.format_response.run(q=q, candidates=candidates, runtime=runtime, trace_id=trace_id)


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


def _dedup_candidates(candidates: list) -> list:
    """Dedup by chunk_id while keeping ordering stable.

    D-4 scope: scores across dense/sparse are not comparable; prefer dense when duplicated.
    """
    best: dict[str, Any] = {}
    order: list[str] = []

    for c in candidates:
        cid = getattr(c, "chunk_id", None)
        if not isinstance(cid, str) or not cid:
            continue
        if cid not in best:
            best[cid] = c
            order.append(cid)
            continue

        prev = best[cid]
        prev_src = getattr(prev, "source", "")
        cur_src = getattr(c, "source", "")
        if prev_src == "dense" and cur_src != "dense":
            continue
        if cur_src == "dense" and prev_src != "dense":
            best[cid] = c
            continue

        # Same source or both non-dense: keep the larger score.
        try:
            if float(getattr(c, "score", 0.0)) > float(getattr(prev, "score", 0.0)):
                best[cid] = c
        except Exception:
            continue

    return [best[cid] for cid in order if cid in best]
