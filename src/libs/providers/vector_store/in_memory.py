from __future__ import annotations

import math
from dataclasses import dataclass, field

from ...interfaces.vector_store.store import VectorItem


@dataclass
class InMemoryVectorIndex:
    """Simple in-memory vector index for local/dev use."""

    _items: dict[str, VectorItem] = field(default_factory=dict)
    _norms: dict[str, float] = field(default_factory=dict)

    def upsert(self, items: list[VectorItem]) -> None:
        for item in items:
            self._items[item.chunk_id] = item
            self._norms[item.chunk_id] = _norm(item.vector)

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        if not self._items:
            return []

        q_norm = _norm(vector)
        scored: list[tuple[str, float]] = []
        for chunk_id, item in self._items.items():
            score = _cosine(vector, q_norm, item.vector, self._norms.get(chunk_id, 0.0))
            scored.append((chunk_id, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete(self, chunk_ids: list[str]) -> None:
        for cid in chunk_ids:
            self._items.pop(cid, None)
            self._norms.pop(cid, None)


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def _cosine(a: list[float], a_norm: float, b: list[float], b_norm: float) -> float:
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (a_norm * b_norm)
