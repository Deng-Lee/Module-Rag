from __future__ import annotations

from pathlib import Path

from src.ingestion.stages.storage.fts5 import Fts5Store


def test_fts5_store_upsert_and_query(tmp_path: Path) -> None:
    db_path = tmp_path / "fts.sqlite"
    store = Fts5Store(db_path=db_path)

    store.upsert(
        [
            ("chk_1", "rag uses chroma"),
            ("chk_2", "sqlite fts5 bm25"),
            ("chk_3", "rag uses sqlite fts5"),
        ]
    )

    hits = store.query("sqlite", top_k=10)
    hit_ids = {cid for cid, _ in hits}
    assert {"chk_2", "chk_3"}.issubset(hit_ids)

    # Replace content for chk_2 and ensure query updates.
    store.upsert([("chk_2", "nothing to see here")])
    hits2 = store.query("bm25", top_k=10)
    hit2_ids = {cid for cid, _ in hits2}
    assert "chk_2" not in hit2_ids

