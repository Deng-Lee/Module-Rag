from __future__ import annotations

import json
import math
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...interfaces.vector_store.store import VectorItem


@dataclass
class ChromaLiteVectorIndex:
    """SQLite-backed vector index (dev-only stand-in for Chroma).

    Stores vectors + metadata and supports a naive full-scan cosine Top-K.
    """

    db_path: str = "data/chroma/chroma_lite.sqlite"

    def __post_init__(self) -> None:
        p = Path(self.db_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._init_db(p)

    def upsert(self, items: list[VectorItem]) -> None:
        if not items:
            return
        with self._connect() as conn:
            for it in items:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO vectors(chunk_id, dim, vector_json, metadata_json, updated_at)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        it.chunk_id,
                        len(it.vector),
                        json.dumps(it.vector, separators=(",", ":")),
                        json.dumps(it.metadata or {}, separators=(",", ":")),
                        time.time(),
                    ),
                )

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []

        qn = _norm(vector)
        scored: list[tuple[str, float]] = []

        with self._connect() as conn:
            rows = conn.execute("SELECT chunk_id, vector_json FROM vectors").fetchall()

        for row in rows:
            vec = json.loads(row["vector_json"])
            score = _cosine(vector, qn, vec)
            scored.append((row["chunk_id"], score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM vectors").fetchone()
        return int(row["c"] if row else 0)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self, p: Path) -> None:
        with sqlite3.connect(p) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vectors (
                    chunk_id TEXT PRIMARY KEY,
                    dim INTEGER,
                    vector_json TEXT,
                    metadata_json TEXT,
                    updated_at REAL
                )
                """
            )


def _norm(vec: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vec))


def _cosine(a: list[float], a_norm: float, b: list[float]) -> float:
    b_norm = _norm(b)
    if a_norm == 0.0 or b_norm == 0.0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (a_norm * b_norm)
