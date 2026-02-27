from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.vector_store import VectorIndex, VectorItem


@dataclass
class ChromaStore:
    """Storage adapter for dense vectors.

    This is a thin wrapper around a `VectorIndex` implementation. In local/dev,
    `vector.chroma_lite` persists to `data/chroma` without external deps.
    """

    index: VectorIndex

    def upsert(self, items: list[VectorItem]) -> None:
        self.index.upsert(items)
