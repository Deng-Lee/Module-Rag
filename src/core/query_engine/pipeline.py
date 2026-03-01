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
from .stages.rerank import RerankStage
from .stages.context_build import ContextBuildStage
from .stages.generate import GenerateStage


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
    rerank: RerankStage = field(default_factory=RerankStage)
    context_build: ContextBuildStage = field(default_factory=ContextBuildStage)
    generate: GenerateStage = field(default_factory=GenerateStage)
    format_response: FormatResponseStage = field(default_factory=FormatResponseStage)

    def run(self, query: str, *, runtime: QueryRuntime, params: QueryParams) -> ResponseIR:
        trace_id = TraceContext.current().trace_id if TraceContext.current() else ""

        with obs.with_stage("query_norm"):
            q = query_norm(query)
            obs.event("query.normalized", {"query_hash": q.query_hash, "rewrite_used": q.rewrite_used})
            ctx = TraceContext.current()
            if ctx is not None:
                ctx.replay_keys["query_hash"] = q.query_hash
                if q.rewrite_used:
                    ctx.replay_keys["rewrite_used"] = True

        with obs.with_stage("retrieve_dense", {"top_k": params.top_k}):
            dense = self.retrieve_dense.run(q, runtime, params)
            _emit_candidates_event("dense", dense, top_k=params.top_k)

        with obs.with_stage("retrieve_sparse", {"top_k": params.top_k}):
            sparse = self.retrieve_sparse.run(q, runtime, params)
            _emit_candidates_event("sparse", sparse, top_k=params.top_k)

        candidates_by_source = {"dense": dense, "sparse": sparse}
        with obs.with_stage("fusion"):
            ranked = self.fusion.run(runtime=runtime, params=params, candidates_by_source=candidates_by_source)
            _emit_ranked_event(ranked, top_k=params.top_k)

        with obs.with_stage("rerank"):
            ranked = self.rerank.run(q=q, runtime=runtime, params=params, ranked=ranked)
            ctx = TraceContext.current()
            if ctx is not None:
                ctx.replay_keys["ranked_chunk_ids"] = [r.chunk_id for r in ranked[: max(0, params.top_k)]]

        with obs.with_stage("context_build"):
            bundle = self.context_build.run(q=q, runtime=runtime, params=params, ranked=ranked)

        with obs.with_stage("generate"):
            gen = self.generate.run(q=q, bundle=bundle, runtime=runtime, params=params)

        with obs.with_stage("format_response"):
            return self.format_response.run(q=q, bundle=bundle, gen=gen, trace_id=trace_id)


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
