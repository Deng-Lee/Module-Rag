from __future__ import annotations

from pathlib import Path

from src.core.query_engine.models import QueryIR, QueryParams, QueryRuntime
from src.core.query_engine.stages.retrieve_sparse import SparseRetrieveStage
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.vector_store.in_memory import InMemoryVectorIndex
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever


def test_sparse_retrieve_stage_disabled_returns_empty() -> None:
    embedder = FakeEmbedder(dim=8)
    vec = InMemoryVectorIndex()
    dense = ChromaDenseRetriever(embedder=embedder, vector_index=vec)
    rt = QueryRuntime(
        embedder=embedder,
        vector_index=vec,
        retriever=dense,
        sqlite=SqliteStore(db_path=Path("cache/test_sparse_retrieve.sqlite")),
        sparse_retriever=None,
        fusion=None,
    )
    q = QueryIR(query_raw="hi", query_norm="hi")
    out = SparseRetrieveStage().run(q, rt, QueryParams(top_k=3))
    assert out == []
