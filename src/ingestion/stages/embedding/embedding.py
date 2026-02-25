from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.embedding import Embedder
from ....libs.interfaces.splitter import ChunkIR
from ....libs.providers.embedding.cache import EmbeddingCache
from .dense import DenseEncoder
from .models import DenseEncoded, EncodedChunks, SparseEncoded
from .sparse import SparseEncoderStage


@dataclass
class EncodingStrategy:
    mode: str  # dense|sparse|hybrid


@dataclass
class EmbeddingStage:
    embedder: Embedder
    cache: EmbeddingCache | None = None
    embedder_id: str = "embedder.unknown"
    embedder_version: str = "0"

    def run(self, chunks: list[ChunkIR], encoding_strategy: EncodingStrategy) -> EncodedChunks:
        mode = encoding_strategy.mode
        if mode not in {"dense", "sparse", "hybrid"}:
            raise ValueError(f"unknown encoding mode: {mode}")

        out = EncodedChunks(chunks=chunks)

        if mode in {"dense", "hybrid"}:
            dense_items, hits, misses = DenseEncoder(
                self.embedder,
                cache=self.cache,
                embedder_id=self.embedder_id,
                embedder_version=self.embedder_version,
            ).encode(chunks)
            out.dense = DenseEncoded(items=dense_items, cache_hits=hits, cache_misses=misses)

        if mode in {"sparse", "hybrid"}:
            sparse_docs = SparseEncoderStage().encode(chunks)
            out.sparse = SparseEncoded(docs=sparse_docs)

        return out
