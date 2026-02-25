from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.embedding import Embedder
from ....libs.interfaces.splitter import ChunkIR
from .dense import DenseEncoder
from .models import DenseEncoded, EncodedChunks, SparseEncoded
from .sparse import SparseEncoderStage


@dataclass
class EncodingStrategy:
    mode: str  # dense|sparse|hybrid


@dataclass
class EmbeddingStage:
    embedder: Embedder

    def run(self, chunks: list[ChunkIR], encoding_strategy: EncodingStrategy) -> EncodedChunks:
        mode = encoding_strategy.mode
        if mode not in {"dense", "sparse", "hybrid"}:
            raise ValueError(f"unknown encoding mode: {mode}")

        out = EncodedChunks(chunks=chunks)

        if mode in {"dense", "hybrid"}:
            dense_items = DenseEncoder(self.embedder).encode(chunks)
            out.dense = DenseEncoded(items=dense_items)

        if mode in {"sparse", "hybrid"}:
            sparse_docs = SparseEncoderStage().encode(chunks)
            out.sparse = SparseEncoded(docs=sparse_docs)

        return out
