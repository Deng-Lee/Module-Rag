from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...interfaces.vector_store.store import VectorItem


@dataclass
class ChromaVectorIndex:
    """Chroma-backed VectorIndex (persistent).

    Requires the external `chromadb` dependency.
    """

    persist_dir: str = "data/chroma/chroma"
    collection: str = "chunks"
    space: str = "cosine"  # cosine|l2|ip (depends on Chroma/hnsw)

    def __post_init__(self) -> None:
        try:
            import chromadb  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("dependency_missing:chromadb") from exc

        p = Path(self.persist_dir)
        p.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(p))
        # For hnsw, `hnsw:space` controls distance semantics.
        meta = {"hnsw:space": self.space} if self.space else {}
        self._col = self._client.get_or_create_collection(name=self.collection, metadata=meta or None)

    def upsert(self, items: list[VectorItem]) -> None:
        if not items:
            return
        ids = [it.chunk_id for it in items]
        embs = [it.vector for it in items]
        metas = [it.metadata or {} for it in items]
        self._col.upsert(ids=ids, embeddings=embs, metadatas=metas)

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        res: Any = self._col.query(query_embeddings=[vector], n_results=int(top_k), include=["distances", "ids"])
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out: list[tuple[str, float]] = []
        for cid, dist in zip(ids, dists):
            out.append((str(cid), _distance_to_score(float(dist), space=self.space)))
        return out

    def delete(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self._col.delete(ids=list(chunk_ids))


def _distance_to_score(dist: float, *, space: str) -> float:
    # Chroma returns a distance; convert to "larger is better" score.
    # - cosine: distance ~= 1 - cosine_similarity
    # - l2: smaller is better -> score = -dist
    # - ip: depending on backend, may already be negative inner product; treat as -dist.
    sp = (space or "").lower()
    if sp == "cosine":
        return 1.0 - dist
    return -dist

