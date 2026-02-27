from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Fts5Store:
    db_path: Path

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                USING fts5(chunk_id, text)
                """
            )

    def upsert(self, docs: list[tuple[str, str]]) -> None:
        with self._connect() as conn:
            for chunk_id, text in docs:
                conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
                conn.execute(
                    "INSERT INTO chunks_fts(chunk_id, text) VALUES(?, ?)",
                    (chunk_id, text),
                )

    def query(self, query_expr: str, top_k: int) -> list[tuple[str, float]]:
        if top_k <= 0:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chunk_id, bm25(chunks_fts) AS score FROM chunks_fts WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?",
                (query_expr, top_k),
            ).fetchall()
        return [(r["chunk_id"], float(r["score"])) for r in rows]
