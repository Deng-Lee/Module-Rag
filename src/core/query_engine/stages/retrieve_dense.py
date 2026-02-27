from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.vector_store import Candidate
from ....libs.providers.embedding.cache import canonical
from ..models import QueryIR, QueryParams, QueryRuntime


@dataclass
class DenseRetrieveStage:
    """Dense-only retrieval using VectorIndex.query (no fusion/rerank yet)."""

    def run(self, q: QueryIR, runtime: QueryRuntime, params: QueryParams) -> list[Candidate]:
        if params.top_k <= 0:
            return []
        if not q.query_norm.strip():
            return []

        # Align with ingestion embedding input: canonicalize using the same profile.
        emb_in = canonical(q.query_norm, profile_id=params.text_norm_profile_id)
        vec = runtime.embedder.embed_texts([emb_in])[0]
        hits = runtime.vector_index.query(vec, params.top_k)
        return [Candidate(chunk_id=cid, score=float(score), source="dense") for cid, score in hits]

