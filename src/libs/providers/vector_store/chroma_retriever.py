from __future__ import annotations

from dataclasses import dataclass

from ...interfaces.embedding import Embedder
from ...interfaces.vector_store import Candidate, Retriever, VectorIndex
from ..embedding.cache import canonical


@dataclass
class ChromaDenseRetriever(Retriever):
    """Dense retriever backed by a VectorIndex (Chroma/ChromaLite/InMemory).

    Note: despite the name, this works with any `VectorIndex` implementation.
    """

    embedder: Embedder
    vector_index: VectorIndex
    text_norm_profile_id: str = "default"
    source_name: str = "dense"

    def retrieve(self, query: str, top_k: int) -> list[Candidate]:
        if top_k <= 0:
            return []
        q = (query or "").strip()
        if not q:
            return []

        emb_in = canonical(q, profile_id=self.text_norm_profile_id)
        vec = self.embedder.embed_texts([emb_in])[0]
        hits = self.vector_index.query(vec, top_k)
        return [Candidate(chunk_id=cid, score=float(score), source=self.source_name) for cid, score in hits]

