from __future__ import annotations

import time
from dataclasses import dataclass

from ....libs.interfaces.vector_store import RankedCandidate
from ....observability.obs import api as obs
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
        started_at = time.perf_counter()
        provider_id = runtime.reranker_provider_id or "noop"
        rerank_profile_id = runtime.rerank_profile_id

        if runtime.reranker is None:
            obs.event(
                "rerank.skipped",
                {
                    "reason": "no_reranker",
                    "count": len(ranked),
                    "provider_id": provider_id,
                    "rerank_profile_id": rerank_profile_id,
                    "rerank_applied": False,
                    "rerank_failed": False,
                    "effective_rank_source": "fusion",
                },
            )
            _emit_rerank_latency(started_at, provider_id=provider_id)
            return ranked

        try:
            # Attach chunk text/metadata for rerankers that need content (LLM / cross-encoder).
            before_preview = [
                {
                    "chunk_id": r.chunk_id,
                    "rank": int(getattr(r, "rank", 0) or 0),
                    "score": float(r.score),
                }
                for r in ranked[: min(10, len(ranked))]
            ]
            chunk_ids = [r.chunk_id for r in ranked if r.chunk_id]
            rows = runtime.sqlite.fetch_chunks(chunk_ids)
            by_id = {r.chunk_id: r for r in rows}
            used_retrieval_view = False
            for r in ranked:
                row = by_id.get(r.chunk_id)
                if row is None:
                    continue
                if not isinstance(r.metadata, dict):
                    r.metadata = {}
                r.metadata["chunk_text"] = row.chunk_text
                rerank_text = (
                    row.chunk_retrieval_text
                    if row.chunk_retrieval_text
                    else row.chunk_text
                )
                if row.chunk_retrieval_text:
                    used_retrieval_view = True
                r.metadata["rerank_text"] = rerank_text
                r.metadata["section_path"] = row.section_path
                r.metadata["doc_id"] = row.doc_id
                r.metadata["version_id"] = row.version_id

            out = runtime.reranker.rerank(q.query_norm, ranked)
            if not isinstance(out, list):
                raise TypeError("reranker returned non-list")
            # Ensure ranks are sequential after rerank.
            for i, r in enumerate(out, start=1):
                r.rank = i
            after_preview = [
                {
                    "chunk_id": r.chunk_id,
                    "rank": int(getattr(r, "rank", 0) or 0),
                    "score": float(r.score),
                }
                for r in out[: min(10, len(out))]
            ]
            obs.event(
                "rerank.ranked",
                {"before": before_preview, "after": after_preview},
            )
            obs.event(
                "rerank.used",
                {
                    "count_in": len(ranked),
                    "count_out": len(out),
                    "provider": type(runtime.reranker).__name__,
                    "provider_id": provider_id,
                    "rerank_profile_id": rerank_profile_id,
                    "text_source": "retrieval_view" if used_retrieval_view else "facts",
                    "rerank_applied": True,
                    "rerank_failed": False,
                    "effective_rank_source": "rerank",
                },
            )
            _emit_rerank_latency(started_at, provider_id=provider_id)
            return out
        except Exception as e:
            obs.event(
                "warn.rerank_fallback",
                {
                    "exc_type": type(e).__name__,
                    "message": str(e),
                    "count": len(ranked),
                    "provider_id": provider_id,
                    "rerank_profile_id": rerank_profile_id,
                    "rerank_failed": True,
                    "effective_rank_source": "fusion",
                },
            )
            obs.event(
                "rerank.used",
                {
                    "count_in": len(ranked),
                    "count_out": len(ranked),
                    "provider": type(runtime.reranker).__name__,
                    "provider_id": provider_id,
                    "rerank_profile_id": rerank_profile_id,
                    "text_source": "retrieval_view" if used_retrieval_view else "facts",
                    "rerank_applied": False,
                    "rerank_failed": True,
                    "effective_rank_source": "fusion",
                },
            )
            _emit_rerank_latency(started_at, provider_id=provider_id)
            return ranked


def _emit_rerank_latency(started_at: float, *, provider_id: str) -> None:
    elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 3)
    obs.metric("rerank_latency_ms", elapsed_ms, {"provider_id": provider_id})
