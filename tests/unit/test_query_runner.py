from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from src.core.query_engine.models import QueryRuntime
from src.core.runners import QueryRunner
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.libs.interfaces.vector_store import VectorItem
from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.llm.fake_llm import FakeLLM
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever
from src.libs.providers.vector_store.in_memory import InMemoryVectorIndex


def test_query_runner_spans_and_extractive_response(tmp_path: Path) -> None:
    # prepare stores
    sqlite = SqliteStore(db_path=tmp_path / "app.sqlite")
    vec = InMemoryVectorIndex()
    embedder = FakeEmbedder(dim=8)

    # one chunk in "DB"
    chunk_id = "chk_test_1"
    doc_id = "doc_1"
    version_id = "ver_1"
    sqlite.upsert_doc_version_minimal(doc_id, version_id, file_sha256="h", status="indexed")
    sqlite.upsert_chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        version_id=version_id,
        section_id="sec_1",
        section_path="Install",
        chunk_index=1,
        chunk_text="hello world from chunk",
    )
    sqlite.upsert_chunk_asset(chunk_id=chunk_id, asset_id="a_test_asset")

    # vector index stores the same embedding as the query will compute (stable top-1).
    q = "hello world from chunk"
    q_vec = embedder.embed_texts([q])[0]
    vec.upsert(
        [
            VectorItem(
                chunk_id=chunk_id,
                vector=q_vec,
                metadata={"doc_id": doc_id, "version_id": version_id},
            )
        ]
    )

    def build_rt(_: str) -> QueryRuntime:
        return QueryRuntime(
            embedder=embedder,
            vector_index=vec,
            retriever=ChromaDenseRetriever(embedder=embedder, vector_index=vec),
            sparse_retriever=None,
            sqlite=sqlite,
            fusion=None,
            reranker=None,
            llm=FakeLLM(name="fake-llm"),
        )

    runner = QueryRunner(runtime_builder=build_rt)
    resp = runner.run(q, strategy_config_id="local.default", top_k=3)

    assert resp.trace_id
    assert resp.trace is not None
    assert [s.name for s in resp.trace.spans] == [
        "stage.query_norm",
        "stage.retrieve_dense",
        "stage.retrieve_sparse",
        "stage.fusion",
        "stage.rerank",
        "stage.context_build",
        "stage.generate",
        "stage.format_response",
    ]
    assert "Install" in resp.content_md
    assert chunk_id in resp.content_md
    assert resp.sources and resp.sources[0].chunk_id == chunk_id
    assert resp.sources[0].citation_id == "[1]"
    assert resp.sources[0].asset_ids == ["a_test_asset"]

    # D-4: candidates preview events for each source are recorded.
    ev_kinds = []
    for s in resp.trace.spans:
        ev_kinds.extend([e.kind for e in s.events])
    assert "retrieval.candidates" in ev_kinds
    assert "retrieval.fused" in ev_kinds

    # F-6: replay keys include query_hash + ranked_chunk_ids.
    q_hash = sha256(q.strip().encode("utf-8")).hexdigest()
    assert resp.trace.replay["query_hash"] == q_hash
    assert chunk_id in resp.trace.replay.get("ranked_chunk_ids", [])
    assert resp.trace.aggregates["effective_rank_source"] == "fusion"
    assert resp.trace.aggregates["rerank_applied"] is False
    assert resp.trace.aggregates["rerank_failed"] is False
    assert "rerank_latency_ms" in resp.trace.aggregates


def test_query_runner_empty_query() -> None:
    embedder = FakeEmbedder()
    vec = InMemoryVectorIndex()
    sqlite = SqliteStore(db_path=Path(":memory:"))  # type: ignore[arg-type]
    retriever = ChromaDenseRetriever(embedder=embedder, vector_index=vec)
    runner = QueryRunner(
        runtime_builder=lambda _: QueryRuntime(
            embedder=embedder,
            vector_index=vec,
            retriever=retriever,
            sparse_retriever=None,
            sqlite=sqlite,
            fusion=None,
            reranker=None,
            llm=None,
        )
    )  # type: ignore[arg-type]
    resp = runner.run("   ", strategy_config_id="local.default", top_k=3)
    assert "空查询" in resp.content_md


def test_query_runner_settings_trace_includes_rerank_profile_id(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        "\n".join(
            [
                "paths:",
                f"  data_dir: {data_dir.as_posix()}",
                f"  raw_dir: {(data_dir / 'raw').as_posix()}",
                f"  md_dir: {(data_dir / 'md').as_posix()}",
                f"  assets_dir: {(data_dir / 'assets').as_posix()}",
                f"  chroma_dir: {(data_dir / 'chroma').as_posix()}",
                f"  sqlite_dir: {(data_dir / 'sqlite').as_posix()}",
                "  cache_dir: cache",
                "  logs_dir: logs",
                "",
                "defaults:",
                "  strategy_config_id: local.test",
            ]
        ),
        encoding="utf-8",
    )

    runner = QueryRunner(settings_path=settings_path)
    resp = runner.run("no results expected", strategy_config_id="local.test", top_k=1)

    assert resp.trace is not None
    assert resp.trace.providers["reranker"]["provider_id"] == "noop"
    assert resp.trace.providers["reranker"]["rerank_profile_id"] == "noop.default"
