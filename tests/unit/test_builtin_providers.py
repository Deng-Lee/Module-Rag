from __future__ import annotations

from src.libs.providers.bootstrap import register_builtin_providers
from src.libs.providers.embedding import FakeEmbedder
from src.libs.providers.llm import FakeLLM
from src.libs.providers.loader import MarkdownLoader, PdfLoader
from src.libs.providers.reranker import NoopReranker
from src.libs.providers.splitter import MarkdownHeadingsSectioner, RecursiveCharChunkerWithinSection
from src.libs.providers.vector_store import InMemoryVectorIndex
from src.libs.registry import ProviderRegistry
from src.libs.interfaces.vector_store.store import VectorItem
from src.libs.interfaces.vector_store.retriever import RankedCandidate


def test_fake_embedder_deterministic() -> None:
    embedder = FakeEmbedder(dim=8)
    v1 = embedder.embed_texts(["hello"])[0]
    v2 = embedder.embed_texts(["hello"])[0]
    v3 = embedder.embed_texts(["world"])[0]
    assert v1 == v2
    assert v1 != v3
    assert len(v1) == 8


def test_fake_llm_generate() -> None:
    llm = FakeLLM(name="fake")
    result = llm.generate("answer", [{"role": "user", "content": "hi"}])
    assert result.text.startswith("[fake:answer]")


def test_in_memory_vector_index_query() -> None:
    index = InMemoryVectorIndex()
    index.upsert(
        [
            VectorItem(chunk_id="a", vector=[1.0, 0.0]),
            VectorItem(chunk_id="b", vector=[0.0, 1.0]),
        ]
    )
    top = index.query([1.0, 0.0], top_k=1)
    assert top[0][0] == "a"


def test_noop_reranker_preserves_order() -> None:
    reranker = NoopReranker()
    candidates = [
        RankedCandidate(chunk_id="a", score=1.0, rank=1, source="dense"),
        RankedCandidate(chunk_id="b", score=0.5, rank=2, source="dense"),
    ]
    assert reranker.rerank("q", candidates) == candidates


def test_register_builtin_providers() -> None:
    reg = ProviderRegistry()
    register_builtin_providers(reg)

    assert reg.has("embedder", "embedder.fake")
    assert reg.has("embedder", "embedder.fake_alt")
    assert reg.has("loader", "loader.markdown")
    assert reg.has("loader", "loader.pdf")
    assert reg.has("sectioner", "sectioner.markdown_headings")
    assert reg.has("chunker", "chunker.rcts_within_section")
    assert reg.has("llm", "llm.fake")
    assert reg.has("vector_index", "vector.in_memory")
    assert reg.has("reranker", "reranker.noop")

    assert isinstance(reg.create("embedder", "embedder.fake"), FakeEmbedder)
    assert isinstance(reg.create("embedder", "embedder.fake_alt"), FakeEmbedder)
    assert isinstance(reg.create("loader", "loader.markdown"), MarkdownLoader)
    assert isinstance(reg.create("loader", "loader.pdf"), PdfLoader)
    assert isinstance(reg.create("sectioner", "sectioner.markdown_headings"), MarkdownHeadingsSectioner)
    assert isinstance(reg.create("chunker", "chunker.rcts_within_section"), RecursiveCharChunkerWithinSection)
    assert isinstance(reg.create("llm", "llm.fake"), FakeLLM)
    assert isinstance(reg.create("vector_index", "vector.in_memory"), InMemoryVectorIndex)
    assert isinstance(reg.create("reranker", "reranker.noop"), NoopReranker)
