from __future__ import annotations

from pathlib import Path

from src.core.query_engine.models import QueryRuntime
from src.core.runners import QueryRunner
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.libs.interfaces.vector_store import Candidate, RankedCandidate
from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.llm.fake_llm import FakeLLM
from src.libs.providers.reranker.cross_encoder import CrossEncoderReranker
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever
from src.libs.providers.vector_store.in_memory import InMemoryVectorIndex


class _BoomReranker:
    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        raise RuntimeError("boom")


class _CaptureReranker:
    def __init__(self) -> None:
        self.last_texts: list[str] = []
        self.last_chunk_texts: list[str] = []

    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        self.last_texts = []
        self.last_chunk_texts = []
        for c in candidates:
            text = ""
            chunk_text = ""
            if isinstance(c.metadata, dict):
                v = c.metadata.get("rerank_text")
                if isinstance(v, str):
                    text = v
                facts = c.metadata.get("chunk_text")
                if isinstance(facts, str):
                    chunk_text = facts
            self.last_texts.append(text)
            self.last_chunk_texts.append(chunk_text)
        return candidates


class _FixedRetriever:
    def __init__(self, candidates: list[Candidate]) -> None:
        self._candidates = list(candidates)

    def retrieve(self, query: str, top_k: int) -> list[Candidate]:
        _ = query
        return list(self._candidates[:top_k])


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
            llm=FakeLLM(name="fake-llm"),
        )

    resp = QueryRunner(runtime_builder=build_rt).run(
        "hello",
        strategy_config_id="local.default",
        top_k=3,
    )
    assert resp.trace is not None
    # warning event should be present under stage.rerank span
    rerank_span = [s for s in resp.trace.spans if s.name == "stage.rerank"][0]
    assert any(e.kind == "warn.rerank_fallback" for e in rerank_span.events)
    used_events = [e for e in rerank_span.events if e.kind == "rerank.used"]
    assert used_events
    assert used_events[-1].attrs.get("rerank_failed") is True
    assert used_events[-1].attrs.get("effective_rank_source") == "fusion"
    assert resp.trace.aggregates.get("rerank_failed") is True
    assert resp.trace.aggregates.get("effective_rank_source") == "fusion"
    assert "rerank_latency_ms" in resp.trace.aggregates


def test_rerank_prefers_retrieval_view_text(tmp_path: Path) -> None:
    sqlite = SqliteStore(db_path=tmp_path / "app.sqlite")
    embedder = FakeEmbedder(dim=8)

    sqlite.upsert_doc_version_minimal("doc_1", "ver_1", file_sha256="h", status="indexed")
    sqlite.upsert_chunk(
        chunk_id="chk_1",
        doc_id="doc_1",
        version_id="ver_1",
        section_id="sec_1",
        section_path="Title",
        chunk_index=1,
        chunk_text="facts text",
        chunk_retrieval_text="retrieval view text",
    )
    cap = _CaptureReranker()

    def build_rt(_: str) -> QueryRuntime:
        return QueryRuntime(
            embedder=embedder,
            vector_index=InMemoryVectorIndex(),
            retriever=_FixedRetriever(
                [
                    Candidate(
                        chunk_id="chk_1",
                        score=1.0,
                        source="dense",
                        metadata={
                            "chunk_text": "stale facts text",
                            "rerank_text": "stale retrieval view text",
                        },
                    )
                ]
            ),
            sqlite=sqlite,
            sparse_retriever=None,
            fusion=None,
            reranker=cap,
            llm=FakeLLM(name="fake-llm"),
        )

    resp = QueryRunner(runtime_builder=build_rt).run(
        "facts text",
        strategy_config_id="local.default",
        top_k=3,
    )
    assert cap.last_texts == ["retrieval view text"]
    assert cap.last_chunk_texts == ["facts text"]
    rerank_span = [s for s in resp.trace.spans if s.name == "stage.rerank"][0]
    used_events = [e for e in rerank_span.events if e.kind == "rerank.used"]
    assert used_events
    assert used_events[-1].attrs.get("text_source") == "retrieval_view"
    assert used_events[-1].attrs.get("rerank_applied") is True
    assert used_events[-1].attrs.get("effective_rank_source") == "rerank"
    assert resp.trace.aggregates.get("rerank_profile_id") is None


def test_cross_encoder_failure_falls_back_without_breaking_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    sqlite = SqliteStore(db_path=tmp_path / "app.sqlite")
    vec = InMemoryVectorIndex()
    embedder = FakeEmbedder(dim=8)
    dense = ChromaDenseRetriever(embedder=embedder, vector_index=vec)

    sqlite.upsert_doc_version_minimal("doc_1", "ver_1", file_sha256="h", status="indexed")
    sqlite.upsert_chunk(
        chunk_id="chk_1",
        doc_id="doc_1",
        version_id="ver_1",
        section_id="sec_1",
        section_path="Title",
        chunk_index=1,
        chunk_text="hello",
        chunk_retrieval_text="hello retrieval",
    )
    from src.libs.interfaces.vector_store import VectorItem

    v = embedder.embed_texts(["hello"])[0]
    vec.upsert([VectorItem(chunk_id="chk_1", vector=v)])

    monkeypatch.setattr(
        CrossEncoderReranker,
        "_predict_pairs",
        lambda self, pairs: (_ for _ in ()).throw(RuntimeError("cross_encoder_failed")),
    )

    rr = CrossEncoderReranker(model_name="dummy")

    def build_rt(_: str) -> QueryRuntime:
        return QueryRuntime(
            embedder=embedder,
            vector_index=vec,
            retriever=dense,
            sqlite=sqlite,
            sparse_retriever=None,
            fusion=None,
            reranker=rr,
            llm=FakeLLM(name="fake-llm"),
        )

    resp = QueryRunner(runtime_builder=build_rt).run(
        "hello",
        strategy_config_id="local.default",
        top_k=3,
    )
    assert resp.sources and resp.sources[0].chunk_id == "chk_1"
    rerank_span = [s for s in resp.trace.spans if s.name == "stage.rerank"][0]
    assert any(e.kind == "warn.rerank_fallback" for e in rerank_span.events)
    used_events = [e for e in rerank_span.events if e.kind == "rerank.used"]
    assert used_events[-1].attrs.get("rerank_failed") is True
    assert used_events[-1].attrs.get("effective_rank_source") == "fusion"
