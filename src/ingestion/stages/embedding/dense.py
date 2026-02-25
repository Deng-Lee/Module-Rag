from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.embedding import Embedder
from ....libs.interfaces.splitter import ChunkIR
from ....libs.interfaces.vector_store import VectorItem


@dataclass
class DenseEncoder:
    embedder: Embedder

    def encode(self, chunks: list[ChunkIR]) -> list[VectorItem]:
        texts = [_chunk_retrieval_text(c) for c in chunks]
        vectors = self.embedder.embed_texts(texts)
        if len(vectors) != len(chunks):
            raise ValueError("embedder returned mismatched vector count")

        items: list[VectorItem] = []
        for c, vec, txt in zip(chunks, vectors, texts):
            items.append(
                VectorItem(
                    chunk_id=c.chunk_id,
                    vector=vec,
                    metadata={
                        "section_path": c.section_path,
                        "doc_id": c.metadata.get("doc_id"),
                        "version_id": c.metadata.get("version_id"),
                        "text_norm_profile_id": c.metadata.get("text_norm_profile_id"),
                    },
                )
            )
        return items


def _chunk_retrieval_text(chunk: ChunkIR) -> str:
    v = chunk.metadata.get("chunk_retrieval_text")
    if isinstance(v, str) and v.strip():
        return v
    return chunk.text
