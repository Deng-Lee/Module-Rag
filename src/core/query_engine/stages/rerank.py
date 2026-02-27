from __future__ import annotations

from dataclasses import dataclass

from ....observability.obs import api as obs
from ....libs.interfaces.vector_store import RankedCandidate
from ..models import QueryIR, QueryParams, QueryRuntime


@dataclass
class RerankStage:
    """Optional rerank stage with explicit fallback.

    If reranker is not configured, returns input as-is.
    If reranker raises, falls back to input and emits a warning event.
    """

    def run(
        self,
        *,
        q: QueryIR,
        runtime: QueryRuntime,
        params: QueryParams,
        ranked: list[RankedCandidate],
    ) -> list[RankedCandidate]:
        _ = params  # reserved for k_out/timeout later

        if runtime.reranker is None:
            obs.event("rerank.skipped", {"reason": "no_reranker", "count": len(ranked)})
            return ranked

        try:
            out = runtime.reranker.rerank(q.query_norm, ranked)
            if not isinstance(out, list):
                raise TypeError("reranker returned non-list")
            # Ensure ranks are sequential after rerank.
            for i, r in enumerate(out, start=1):
                r.rank = i
            obs.event("rerank.used", {"count_in": len(ranked), "count_out": len(out), "provider": type(runtime.reranker).__name__})
            return out
        except Exception as e:
            obs.event(
                "warn.rerank_fallback",
                {"exc_type": type(e).__name__, "message": str(e), "count": len(ranked)},
            )
            return ranked

