from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.embedding import Embedder
from ....libs.interfaces.splitter import ChunkIR
from ....libs.interfaces.vector_store import VectorItem
from ....observability.obs import api as obs
from ....libs.providers.embedding.cache import EmbeddingCache, canonical, content_hash, make_embedding_cache_key


@dataclass
class DenseEncoder:
    embedder: Embedder
    cache: EmbeddingCache | None = None
    embedder_id: str = "embedder.unknown"
    embedder_version: str = "0"

    def encode(self, chunks: list[ChunkIR]) -> tuple[list[VectorItem], int, int]:
        inputs: list[str] = []
        keys: list[str] = []
        cached_vectors: list[list[float] | None] = []

        hits = 0
        misses = 0

        for c in chunks:
            raw_text = _chunk_retrieval_text(c)
            profile_id = c.metadata.get("text_norm_profile_id")
            if not isinstance(profile_id, str) or not profile_id:
                profile_id = "default"

            embedding_input = canonical(raw_text, profile_id=profile_id)
            ch = content_hash(raw_text, text_norm_profile_id=profile_id)
            key = make_embedding_cache_key(
                text_norm_profile_id=profile_id,
                content_hash=ch,
                embedder_id=self.embedder_id,
                embedder_version=self.embedder_version,
            )

            if self.cache is None:
                inputs.append(embedding_input)
                keys.append(key)
                cached_vectors.append(None)
                misses += 1
                continue

            vec = self.cache.get(key)
            if vec is not None:
                cached_vectors.append(vec)
                hits += 1
            else:
                cached_vectors.append(None)
                inputs.append(embedding_input)
                keys.append(key)
                misses += 1

        new_vectors: list[list[float]] = []
        if inputs:
            new_vectors = self.embedder.embed_texts(inputs)
            if len(new_vectors) != len(inputs):
                raise ValueError("embedder returned mismatched vector count")

        if self.cache is not None and inputs:
            for key, vec in zip(keys, new_vectors):
                self.cache.put(key, vec)

        # merge vectors back to per-chunk order
        merged: list[list[float]] = []
        it = iter(new_vectors)
        for v in cached_vectors:
            merged.append(v if v is not None else next(it))

        items: list[VectorItem] = []
        for c, vec in zip(chunks, merged):
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

        obs.metric("embedding_cache_hit", hits, {"embedder_id": self.embedder_id})
        obs.metric("embedding_cache_miss", misses, {"embedder_id": self.embedder_id})
        return items, hits, misses


def _chunk_retrieval_text(chunk: ChunkIR) -> str:
    v = chunk.metadata.get("chunk_retrieval_text")
    if isinstance(v, str) and v.strip():
        return v
    return chunk.text
