from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...interfaces.vector_store import Candidate, Retriever
from ....ingestion.stages.storage.fts5 import Fts5Store


_TERM_RE = re.compile(r"[0-9A-Za-z_]+|[\u4e00-\u9fff]+")


def build_fts5_query(query_norm: str) -> str:
    """Build a conservative FTS5 MATCH expression.

    D-3 scope: minimal parser.
    - Drops most punctuation/special operators to avoid surprising semantics.
    - Keeps ASCII word tokens and CJK runs.
    """
    q = (query_norm or "").strip()
    if not q:
        return ""
    terms = _TERM_RE.findall(q)
    return " ".join(t for t in terms if t)


@dataclass
class Fts5Retriever(Retriever):
    """Sparse retriever backed by SQLite FTS5 (BM25).

    Returns Candidate.score where larger is better (we negate bm25).
    """

    db_path: str = "data/sqlite/fts.sqlite"
    source_name: str = "sparse"

    def __post_init__(self) -> None:
        self._store = Fts5Store(db_path=Path(self.db_path))

    def retrieve(self, query: str, top_k: int) -> list[Candidate]:
        if top_k <= 0:
            return []
        qexpr = build_fts5_query(query)
        if not qexpr:
            return []
        hits = self._store.query(qexpr, top_k=top_k)
        out: list[Candidate] = []
        for chunk_id, bm25_score in hits:
            # SQLite's bm25 is "smaller is better"; normalize to "larger is better".
            score = -float(bm25_score)
            out.append(
                Candidate(
                    chunk_id=chunk_id,
                    score=score,
                    source=self.source_name,
                    metadata={"bm25": float(bm25_score), "qexpr": qexpr},
                )
            )
        return out

