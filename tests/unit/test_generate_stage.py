from __future__ import annotations

from src.core.query_engine.stages.generate import GenerateStage
from src.core.query_engine.models import QueryIR, QueryParams, QueryRuntime
from src.core.query_engine.stages.context_build import ContextBundle, ContextChunk
from pathlib import Path

from src.ingestion.stages.storage.sqlite import SqliteStore
from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.llm.fake_llm import FakeLLM
from src.libs.providers.vector_store.in_memory import InMemoryVectorIndex
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever


class _BoomLLM:
    def generate(self, mode: str, messages: list[dict], **kwargs):
        raise RuntimeError("boom")


def _rt(llm) -> QueryRuntime:
    embedder = FakeEmbedder(dim=8)
    idx = InMemoryVectorIndex()
    dense = ChromaDenseRetriever(embedder=embedder, vector_index=idx)
    sqlite = SqliteStore(db_path=Path("cache/test_generate.sqlite"))
    return QueryRuntime(
        embedder=embedder,
        vector_index=idx,
        retriever=dense,
        sqlite=sqlite,
        llm=llm,
    )


def test_generate_stage_uses_llm_when_available() -> None:
    q = QueryIR(query_raw="q", query_norm="what is rag")
    bundle = ContextBundle(
        chunks=[
            ContextChunk(
                chunk_id="chk_1",
                rank=1,
                score=1.0,
                source="rrf",
                doc_id="doc_1",
                version_id="ver_1",
                section_path="Title",
                chunk_index=1,
                chunk_text="rag is retrieval augmented generation",
                excerpt="rag is retrieval augmented generation",
                citation_id="[1]",
                asset_ids=[],
            )
        ],
        citations_md="[1] ...\n",
        debug={},
    )
    res = GenerateStage().run(q=q, bundle=bundle, runtime=_rt(FakeLLM(name="fake-llm")), params=QueryParams())
    assert res.used_llm is True
    assert res.answer_md.startswith("[fake-llm:rag]")


def test_generate_stage_falls_back_on_llm_failure() -> None:
    q = QueryIR(query_raw="q", query_norm="what is rag")
    bundle = ContextBundle(
        chunks=[
            ContextChunk(
                chunk_id="chk_1",
                rank=1,
                score=1.0,
                source="rrf",
                doc_id="doc_1",
                version_id="ver_1",
                section_path="Title",
                chunk_index=1,
                chunk_text="rag is retrieval augmented generation",
                excerpt="rag is retrieval augmented generation",
                citation_id="[1]",
                asset_ids=[],
            )
        ],
        citations_md="[1] ...\n",
        debug={},
    )
    res = GenerateStage().run(q=q, bundle=bundle, runtime=_rt(_BoomLLM()), params=QueryParams())
    assert res.used_llm is False
    assert "extractive fallback" in res.answer_md
