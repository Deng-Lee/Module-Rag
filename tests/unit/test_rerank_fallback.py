from __future__ import annotations

from pathlib import Path

from src.core.runners import QueryRunner
from src.core.query_engine.models import QueryRuntime
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.libs.interfaces.vector_store import RankedCandidate
from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever
from src.libs.providers.vector_store.in_memory import InMemoryVectorIndex


class _BoomReranker:
    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        raise RuntimeError("boom")


def test_rerank_fallback_emits_warning(tmp_path: Path) -> None:
    sqlite = SqliteStore(db_path=tmp_path / "app.sqlite")
    vec = InMemoryVectorIndex()
    embedder = FakeEmbedder(dim=8)
    dense = ChromaDenseRetriever(embedder=embedder, vector_index=vec)

    # DB has one chunk and vector index matches it.
    sqlite.upsert_doc_version_minimal("doc_1", "ver_1", file_sha256="h", status="indexed")
    sqlite.upsert_chunk(
        chunk_id="chk_1",
        doc_id="doc_1",
        version_id="ver_1",
        section_id="sec_1",
        section_path="Title",
        chunk_index=1,
        chunk_text="hello",
    )
    v = embedder.embed_texts(["hello"])[0]
    from src.libs.interfaces.vector_store import VectorItem

    vec.upsert([VectorItem(chunk_id="chk_1", vector=v)])

    def build_rt(_: str) -> QueryRuntime:
        return QueryRuntime(
            embedder=embedder,
            vector_index=vec,
            retriever=dense,
            sqlite=sqlite,
            sparse_retriever=None,
            fusion=None,
            reranker=_BoomReranker(),
        )

    resp = QueryRunner(runtime_builder=build_rt).run("hello", strategy_config_id="local.default", top_k=3)
    assert resp.trace is not None
    # warning event should be present under stage.rerank span
    rerank_span = [s for s in resp.trace.spans if s.name == "stage.rerank"][0]
    assert any(e.kind == "warn.rerank_fallback" for e in rerank_span.events)

