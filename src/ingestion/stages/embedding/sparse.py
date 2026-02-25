from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.splitter import ChunkIR
from .models import SparseDoc


@dataclass
class SparseEncoderStage:
    """Sparse encoding MVP: produce (chunk_id, text) docs for FTS5."""

    def encode(self, chunks: list[ChunkIR]) -> list[SparseDoc]:
        docs: list[SparseDoc] = []
        for c in chunks:
            text = _chunk_retrieval_text(c)
            docs.append(
                SparseDoc(
                    chunk_id=c.chunk_id,
                    text=text,
                    metadata={
                        "section_path": c.section_path,
                        "doc_id": c.metadata.get("doc_id"),
                        "version_id": c.metadata.get("version_id"),
                    },
                )
            )
        return docs


def _chunk_retrieval_text(chunk: ChunkIR) -> str:
    v = chunk.metadata.get("chunk_retrieval_text")
    if isinstance(v, str) and v.strip():
        return v
    return chunk.text
