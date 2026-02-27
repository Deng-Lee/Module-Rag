from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChunkRow:
    chunk_id: str
    doc_id: str
    version_id: str
    section_id: str
    section_path: str
    chunk_index: int
    chunk_text: str


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

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    rel_path TEXT,
                    created_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_refs (
                    ref_id TEXT PRIMARY KEY,
                    asset_id TEXT,
                    doc_id TEXT,
                    version_id TEXT,
                    source_type TEXT,
                    origin_ref TEXT,
                    anchor_json TEXT,
                    created_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id TEXT PRIMARY KEY,
                    doc_id TEXT,
                    version_id TEXT,
                    section_id TEXT,
                    section_path TEXT,
                    chunk_index INTEGER,
                    chunk_text TEXT,
                    created_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunk_assets (
                    chunk_id TEXT,
                    asset_id TEXT,
                    PRIMARY KEY(chunk_id, asset_id)
                )
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

    def set_version_status(self, version_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE doc_versions SET status=? WHERE version_id=?", (status, version_id))

    def upsert_asset(self, asset_id: str, rel_path: str | None = None) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO assets(asset_id, rel_path, created_at) VALUES(?, ?, ?)",
                (asset_id, rel_path, ts),
            )

    def upsert_asset_ref(self, *, ref_id: str, asset_id: str, doc_id: str, version_id: str, source_type: str, origin_ref: str, anchor_json: str) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO asset_refs(ref_id, asset_id, doc_id, version_id, source_type, origin_ref, anchor_json, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ref_id, asset_id, doc_id, version_id, source_type, origin_ref, anchor_json, ts),
            )

    def upsert_chunk(self, *, chunk_id: str, doc_id: str, version_id: str, section_id: str, section_path: str, chunk_index: int, chunk_text: str) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO chunks(chunk_id, doc_id, version_id, section_id, section_path, chunk_index, chunk_text, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, doc_id, version_id, section_id, section_path, chunk_index, chunk_text, ts),
            )

    def upsert_chunk_asset(self, *, chunk_id: str, asset_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chunk_assets(chunk_id, asset_id) VALUES(?, ?)",
                (chunk_id, asset_id),
            )

    def fetch_chunks(self, chunk_ids: list[str]) -> list[ChunkRow]:
        if not chunk_ids:
            return []
        placeholders = ",".join(["?"] * len(chunk_ids))
        sql = f"""
            SELECT chunk_id, doc_id, version_id, section_id, section_path, chunk_index, chunk_text
            FROM chunks
            WHERE chunk_id IN ({placeholders})
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(chunk_ids)).fetchall()

        out: list[ChunkRow] = []
        for r in rows:
            out.append(
                ChunkRow(
                    chunk_id=str(r["chunk_id"]),
                    doc_id=str(r["doc_id"]),
                    version_id=str(r["version_id"]),
                    section_id=str(r["section_id"] or ""),
                    section_path=str(r["section_path"] or ""),
                    chunk_index=int(r["chunk_index"] or 0),
                    chunk_text=str(r["chunk_text"] or ""),
                )
            )
        return out

    def fetch_chunk_assets(self, chunk_ids: list[str]) -> dict[str, list[str]]:
        if not chunk_ids:
            return {}
        placeholders = ",".join(["?"] * len(chunk_ids))
        sql = f"""
            SELECT chunk_id, asset_id
            FROM chunk_assets
            WHERE chunk_id IN ({placeholders})
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(chunk_ids)).fetchall()

        out: dict[str, list[str]] = {}
        for r in rows:
            cid = str(r["chunk_id"])
            aid = str(r["asset_id"])
            out.setdefault(cid, []).append(aid)
        return out


def new_doc_id() -> str:
    return f"doc_{uuid.uuid4().hex}"


def new_version_id() -> str:
    return f"ver_{uuid.uuid4().hex}"
