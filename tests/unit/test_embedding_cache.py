from __future__ import annotations

from src.ingestion.stages import EmbeddingStage, EncodingStrategy
from src.libs.interfaces.splitter import ChunkIR
from src.libs.providers.embedding import FakeEmbedder
from src.libs.providers.embedding.cache import InMemoryEmbeddingCache, make_embedding_cache_key, content_hash


def test_make_embedding_cache_key_stable() -> None:
    ch = content_hash("hello", text_norm_profile_id="default")
    k1 = make_embedding_cache_key(
        text_norm_profile_id="default",
        content_hash=ch,
        embedder_id="embedder.fake",
        embedder_version="0",
    )
    k2 = make_embedding_cache_key(
        text_norm_profile_id="default",
        content_hash=ch,
        embedder_id="embedder.fake",
        embedder_version="0",
    )
    assert k1 == k2


def test_embedding_cache_hit_on_second_run() -> None:
    cache = InMemoryEmbeddingCache()
    stage = EmbeddingStage(
        embedder=FakeEmbedder(dim=4),
        cache=cache,
        embedder_id="embedder.fake",
        embedder_version="0",
    )

    chunks = [ChunkIR(chunk_id="c1", section_path="A", text="facts", metadata={"chunk_retrieval_text": "view"})]

    out1 = stage.run(chunks, EncodingStrategy(mode="dense"))
    assert out1.dense is not None
    assert out1.dense.cache_hits == 0
    assert out1.dense.cache_misses == 1

    out2 = stage.run(chunks, EncodingStrategy(mode="dense"))
    assert out2.dense is not None
    assert out2.dense.cache_hits == 1
    assert out2.dense.cache_misses == 0

    assert out1.dense.items[0].vector == out2.dense.items[0].vector
