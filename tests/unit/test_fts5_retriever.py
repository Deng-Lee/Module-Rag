from __future__ import annotations

from pathlib import Path

from src.ingestion.stages.storage.fts5 import Fts5Store
from src.libs.providers.vector_store.fts5_retriever import Fts5Retriever, build_fts5_query


def test_build_fts5_query_is_conservative() -> None:
    assert build_fts5_query('sqlite fts5 "bm25" (test)') == "sqlite fts5 bm25 test"


def test_fts5_retriever_retrieve(tmp_path: Path) -> None:
    db_path = tmp_path / "fts.sqlite"
    store = Fts5Store(db_path=db_path)
    store.upsert(
        [
            ("chk_1", "rag uses chroma"),
            ("chk_2", "sqlite fts5 bm25"),
            ("chk_3", "rag uses sqlite fts5"),
        ]
    )

    r = Fts5Retriever(db_path=str(db_path))
    hits = r.retrieve("sqlite fts5", top_k=10)
    ids = {h.chunk_id for h in hits}
    assert {"chk_2", "chk_3"}.issubset(ids)

