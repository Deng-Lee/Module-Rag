from __future__ import annotations

import pytest

from src.ingestion.stages import EmbeddingStage, EncodingStrategy
from src.libs.interfaces.splitter import ChunkIR
from src.libs.providers.embedding import FakeEmbedder


def test_embedding_stage_dense_only() -> None:
    chunks = [ChunkIR(chunk_id="c1", section_path="A", text="facts", metadata={"chunk_retrieval_text": "view"})]
    stage = EmbeddingStage(embedder=FakeEmbedder(dim=4))
    out = stage.run(chunks, EncodingStrategy(mode="dense"))

    assert out.dense is not None
    assert out.sparse is None
    assert out.dense.items[0].chunk_id == "c1"
    assert len(out.dense.items[0].vector) == 4


def test_embedding_stage_sparse_only() -> None:
    chunks = [ChunkIR(chunk_id="c1", section_path="A", text="facts", metadata={"chunk_retrieval_text": "view"})]
    stage = EmbeddingStage(embedder=FakeEmbedder(dim=4))
    out = stage.run(chunks, EncodingStrategy(mode="sparse"))

    assert out.dense is None
    assert out.sparse is not None
    assert out.sparse.docs[0].chunk_id == "c1"
    assert out.sparse.docs[0].text == "view"


def test_embedding_stage_hybrid() -> None:
    chunks = [ChunkIR(chunk_id="c1", section_path="A", text="facts", metadata={"chunk_retrieval_text": "view"})]
    stage = EmbeddingStage(embedder=FakeEmbedder(dim=4))
    out = stage.run(chunks, EncodingStrategy(mode="hybrid"))

    assert out.dense is not None
    assert out.sparse is not None


def test_embedding_stage_unknown_mode() -> None:
    chunks = [ChunkIR(chunk_id="c1", section_path="A", text="facts", metadata={})]
    stage = EmbeddingStage(embedder=FakeEmbedder(dim=4))
    with pytest.raises(ValueError):
        stage.run(chunks, EncodingStrategy(mode="unknown"))
