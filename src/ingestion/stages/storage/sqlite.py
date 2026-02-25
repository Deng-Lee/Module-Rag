from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class SqliteStore:
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
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id TEXT PRIMARY KEY,
                    created_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_versions (
                    version_id TEXT PRIMARY KEY,
                    doc_id TEXT,
                    file_sha256 TEXT,
                    status TEXT,
                    created_at REAL,
                    FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_doc_versions_hash
                ON doc_versions(file_sha256)
                """
            )

    def find_version_by_file_hash(self, file_sha256: str) -> tuple[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT doc_id, version_id FROM doc_versions WHERE file_sha256=? LIMIT 1",
                (file_sha256,),
            ).fetchone()
        if row is None:
            return None
        return row["doc_id"], row["version_id"]

    def upsert_doc_version_minimal(
        self, doc_id: str, version_id: str, file_sha256: str, status: str
    ) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO documents(doc_id, created_at) VALUES(?, ?)",
                (doc_id, ts),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO doc_versions(version_id, doc_id, file_sha256, status, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (version_id, doc_id, file_sha256, status, ts),
            )

    def count_versions(self, doc_id: str | None = None) -> int:
        with self._connect() as conn:
            if doc_id is None:
                row = conn.execute("SELECT COUNT(*) AS c FROM doc_versions").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM doc_versions WHERE doc_id=?", (doc_id,)
                ).fetchone()
        return int(row["c"] if row else 0)


def new_doc_id() -> str:
    return f"doc_{uuid.uuid4().hex}"


def new_version_id() -> str:
    return f"ver_{uuid.uuid4().hex}"
