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
            # Attach chunk text/metadata for rerankers that need content (LLM / cross-encoder).
            chunk_ids = [r.chunk_id for r in ranked if r.chunk_id]
            rows = runtime.sqlite.fetch_chunks(chunk_ids)
            by_id = {r.chunk_id: r for r in rows}
            for r in ranked:
                row = by_id.get(r.chunk_id)
                if row is None:
                    continue
                if not isinstance(r.metadata, dict):
                    r.metadata = {}
                r.metadata.setdefault("chunk_text", row.chunk_text)
                r.metadata.setdefault("section_path", row.section_path)
                r.metadata.setdefault("doc_id", row.doc_id)
                r.metadata.setdefault("version_id", row.version_id)

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
