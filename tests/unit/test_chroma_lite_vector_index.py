from __future__ import annotations

from pathlib import Path

from src.libs.providers.vector_store import ChromaLiteVectorIndex
from src.libs.interfaces.vector_store import VectorItem


def test_chroma_lite_upsert_and_query(tmp_path: Path) -> None:
    db = tmp_path / "chroma" / "idx.sqlite"
    idx = ChromaLiteVectorIndex(db_path=str(db))

    idx.upsert(
        [
            VectorItem(chunk_id="a", vector=[1.0, 0.0], metadata={}),
            VectorItem(chunk_id="b", vector=[0.0, 1.0], metadata={}),
        ]
    )

    assert idx.count() == 2
    top = idx.query([1.0, 0.0], top_k=1)
    assert top[0][0] == "a"
