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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS asset_enrichments (
                    asset_id TEXT,
                    provider_id TEXT,
                    model TEXT,
                    profile_id TEXT,
                    ocr_text TEXT,
                    caption_text TEXT,
                    raw_json TEXT,
                    created_at REAL,
                    updated_at REAL,
                    PRIMARY KEY(asset_id, provider_id, model, profile_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunk_enrichments (
                    chunk_id TEXT,
                    provider_id TEXT,
                    model TEXT,
                    profile_id TEXT,
                    retrieval_template_id TEXT,
                    vision_snippets_json TEXT,
                    created_at REAL,
                    updated_at REAL,
                    PRIMARY KEY(chunk_id, provider_id, profile_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS eval_runs (
                    run_id TEXT PRIMARY KEY,
                    dataset_id TEXT,
                    strategy_config_id TEXT,
                    metrics_json TEXT,
                    created_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS eval_case_results (
                    run_id TEXT,
                    case_id TEXT,
                    trace_id TEXT,
                    metrics_json TEXT,
                    artifacts_json TEXT,
                    created_at REAL,
                    PRIMARY KEY(run_id, case_id)
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

    def fetch_version_statuses(self, version_ids: list[str]) -> dict[str, str]:
        if not version_ids:
            return {}
        placeholders = ",".join(["?"] * len(version_ids))
        sql = f"SELECT version_id, status FROM doc_versions WHERE version_id IN ({placeholders})"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(version_ids)).fetchall()
        out: dict[str, str] = {}
        for r in rows:
            out[str(r["version_id"])] = str(r["status"] or "")
        return out

    def mark_deleted(self, *, doc_id: str, version_id: str | None = None) -> dict[str, Any]:
        """Soft delete by setting doc_versions.status='deleted'.

        Returns minimal affected counts for observability.
        """
        with self._connect() as conn:
            if version_id:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM doc_versions WHERE doc_id=? AND version_id=? AND status!='deleted'",
                    (doc_id, version_id),
                ).fetchone()
                versions_marked = int(row["c"] if row else 0)
                conn.execute(
                    "UPDATE doc_versions SET status='deleted' WHERE doc_id=? AND version_id=? AND status!='deleted'",
                    (doc_id, version_id),
                )
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM doc_versions WHERE doc_id=? AND status!='deleted'",
                    (doc_id,),
                ).fetchone()
                versions_marked = int(row["c"] if row else 0)
                conn.execute(
                    "UPDATE doc_versions SET status='deleted' WHERE doc_id=? AND status!='deleted'",
                    (doc_id,),
                )

            # Count chunks under the target scope (best-effort; not a physical delete in E-9).
            if version_id:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM chunks WHERE doc_id=? AND version_id=?",
                    (doc_id, version_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM chunks WHERE doc_id=?",
                    (doc_id,),
                ).fetchone()
            chunks_affected = int(row["c"] if row else 0)

        return {"versions_marked": versions_marked, "chunks_affected": chunks_affected}

    def preview_delete(self, *, doc_id: str, version_id: str | None = None) -> dict[str, Any]:
        """Compute the affected counts of a soft delete without modifying DB."""
        with self._connect() as conn:
            if version_id:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM doc_versions WHERE doc_id=? AND version_id=? AND status!='deleted'",
                    (doc_id, version_id),
                ).fetchone()
                versions_marked = int(row["c"] if row else 0)
                row2 = conn.execute(
                    "SELECT COUNT(*) AS c FROM chunks WHERE doc_id=? AND version_id=?",
                    (doc_id, version_id),
                ).fetchone()
                chunks_affected = int(row2["c"] if row2 else 0)
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM doc_versions WHERE doc_id=? AND status!='deleted'",
                    (doc_id,),
                ).fetchone()
                versions_marked = int(row["c"] if row else 0)
                row2 = conn.execute(
                    "SELECT COUNT(*) AS c FROM chunks WHERE doc_id=?",
                    (doc_id,),
                ).fetchone()
                chunks_affected = int(row2["c"] if row2 else 0)
        return {"versions_marked": versions_marked, "chunks_affected": chunks_affected}

    def fetch_doc_version_ids(self, *, doc_id: str, include_deleted: bool = True) -> list[str]:
        where = "WHERE doc_id=?"
        params: list[Any] = [doc_id]
        if not include_deleted:
            where += " AND status!='deleted'"
        sql = f"SELECT version_id FROM doc_versions {where} ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [str(r["version_id"]) for r in rows]

    def list_doc_versions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False,
        doc_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        if offset < 0:
            offset = 0

        where: list[str] = []
        params: list[Any] = []
        if doc_id:
            where.append("doc_id=?")
            params.append(doc_id)
        if not include_deleted:
            where.append("status!='deleted'")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        sql = f"""
            SELECT doc_id, version_id, file_sha256, status, created_at
            FROM doc_versions
            {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()

        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "doc_id": str(r["doc_id"]),
                    "version_id": str(r["version_id"]),
                    "file_sha256": str(r["file_sha256"] or ""),
                    "status": str(r["status"] or ""),
                    "created_at": float(r["created_at"] or 0.0),
                }
            )
        return out

    def count_docs(self) -> int:
        sql = "SELECT COUNT(*) AS c FROM doc_versions"
        with self._connect() as conn:
            row = conn.execute(sql).fetchone()
        return int(row["c"] if row else 0)

    def count_chunks(self) -> int:
        sql = "SELECT COUNT(*) AS c FROM chunks"
        with self._connect() as conn:
            row = conn.execute(sql).fetchone()
        return int(row["c"] if row else 0)

    def count_assets(self) -> int:
        sql = "SELECT COUNT(*) AS c FROM assets"
        with self._connect() as conn:
            row = conn.execute(sql).fetchone()
        return int(row["c"] if row else 0)

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

    def upsert_asset_enrichment(
        self,
        *,
        asset_id: str,
        provider_id: str,
        model: str,
        profile_id: str,
        ocr_text: str | None = None,
        caption_text: str | None = None,
        raw_json: str | None = None,
    ) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO asset_enrichments(
                    asset_id, provider_id, model, profile_id, ocr_text, caption_text, raw_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT created_at FROM asset_enrichments WHERE asset_id=? AND provider_id=? AND model=? AND profile_id=?),
                    ?
                ), ?)
                """,
                (
                    asset_id,
                    provider_id,
                    model,
                    profile_id,
                    ocr_text,
                    caption_text,
                    raw_json,
                    asset_id,
                    provider_id,
                    model,
                    profile_id,
                    ts,
                    ts,
                ),
            )

    def upsert_chunk_enrichment(
        self,
        *,
        chunk_id: str,
        provider_id: str,
        model: str,
        profile_id: str,
        retrieval_template_id: str | None = None,
        vision_snippets_json: str | None = None,
    ) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO chunk_enrichments(
                    chunk_id, provider_id, model, profile_id, retrieval_template_id, vision_snippets_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT created_at FROM chunk_enrichments WHERE chunk_id=? AND provider_id=? AND profile_id=?),
                    ?
                ), ?)
                """,
                (
                    chunk_id,
                    provider_id,
                    model,
                    profile_id,
                    retrieval_template_id,
                    vision_snippets_json,
                    chunk_id,
                    provider_id,
                    profile_id,
                    ts,
                    ts,
                ),
            )

    def fetch_chunk_enrichments(self, chunk_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not chunk_ids:
            return {}
        placeholders = ",".join(["?"] * len(chunk_ids))
        sql = f"""
            SELECT chunk_id, provider_id, model, profile_id, retrieval_template_id, vision_snippets_json, created_at, updated_at
            FROM chunk_enrichments
            WHERE chunk_id IN ({placeholders})
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(chunk_ids)).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            cid = str(r["chunk_id"])
            out.setdefault(cid, {"items": []})
            out[cid]["items"].append(
                {
                    "provider_id": str(r["provider_id"] or ""),
                    "model": str(r["model"] or ""),
                    "profile_id": str(r["profile_id"] or ""),
                    "retrieval_template_id": str(r["retrieval_template_id"] or ""),
                    "vision_snippets_json": str(r["vision_snippets_json"] or ""),
                    "created_at": float(r["created_at"] or 0.0),
                    "updated_at": float(r["updated_at"] or 0.0),
                }
            )
        return out

    def upsert_eval_run(
        self,
        *,
        run_id: str,
        dataset_id: str,
        strategy_config_id: str,
        metrics_json: str,
    ) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_runs(run_id, dataset_id, strategy_config_id, metrics_json, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (run_id, dataset_id, strategy_config_id, metrics_json, ts),
            )

    def upsert_eval_case_result(
        self,
        *,
        run_id: str,
        case_id: str,
        trace_id: str,
        metrics_json: str,
        artifacts_json: str,
    ) -> None:
        ts = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO eval_case_results(run_id, case_id, trace_id, metrics_json, artifacts_json, created_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (run_id, case_id, trace_id, metrics_json, artifacts_json, ts),
            )

    def list_eval_runs(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        if offset < 0:
            offset = 0
        sql = """
            SELECT run_id, dataset_id, strategy_config_id, metrics_json, created_at
            FROM eval_runs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (limit, offset)).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "run_id": str(r["run_id"]),
                    "dataset_id": str(r["dataset_id"]),
                    "strategy_config_id": str(r["strategy_config_id"]),
                    "metrics_json": str(r["metrics_json"] or "{}"),
                    "created_at": float(r["created_at"] or 0.0),
                }
            )
        return out

    def list_eval_case_results(self, *, run_id: str) -> list[dict[str, Any]]:
        sql = """
            SELECT run_id, case_id, trace_id, metrics_json, artifacts_json, created_at
            FROM eval_case_results
            WHERE run_id=?
            ORDER BY case_id ASC
        """
        with self._connect() as conn:
            rows = conn.execute(sql, (run_id,)).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "run_id": str(r["run_id"]),
                    "case_id": str(r["case_id"]),
                    "trace_id": str(r["trace_id"] or ""),
                    "metrics_json": str(r["metrics_json"] or "{}"),
                    "artifacts_json": str(r["artifacts_json"] or "{}"),
                    "created_at": float(r["created_at"] or 0.0),
                }
            )
        return out

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

    def fetch_assets(self, asset_ids: list[str]) -> dict[str, str | None]:
        """Fetch `asset_id -> rel_path` mapping from assets table (best-effort)."""
        if not asset_ids:
            return {}
        placeholders = ",".join(["?"] * len(asset_ids))
        sql = f"SELECT asset_id, rel_path FROM assets WHERE asset_id IN ({placeholders})"
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(asset_ids)).fetchall()
        out: dict[str, str | None] = {}
        for r in rows:
            out[str(r["asset_id"])] = (str(r["rel_path"]) if r["rel_path"] is not None else None)
        return out

    def fetch_asset_enrichments(self, asset_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not asset_ids:
            return {}
        placeholders = ",".join(["?"] * len(asset_ids))
        sql = f"""
            SELECT asset_id, provider_id, model, profile_id, ocr_text, caption_text, raw_json, created_at, updated_at
            FROM asset_enrichments
            WHERE asset_id IN ({placeholders})
        """
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(asset_ids)).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            aid = str(r["asset_id"])
            out.setdefault(aid, {"items": []})
            out[aid]["items"].append(
                {
                    "provider_id": str(r["provider_id"] or ""),
                    "model": str(r["model"] or ""),
                    "profile_id": str(r["profile_id"] or ""),
                    "ocr_text": str(r["ocr_text"] or ""),
                    "caption_text": str(r["caption_text"] or ""),
                    "raw_json": str(r["raw_json"] or ""),
                    "created_at": float(r["created_at"] or 0.0),
                    "updated_at": float(r["updated_at"] or 0.0),
                }
            )
        return out

    def fetch_doc_version_hashes(self, *, doc_id: str, version_id: str | None = None) -> list[str]:
        if version_id:
            sql = "SELECT file_sha256 FROM doc_versions WHERE doc_id=? AND version_id=?"
            params = (doc_id, version_id)
        else:
            sql = "SELECT file_sha256 FROM doc_versions WHERE doc_id=?"
            params = (doc_id,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [str(r["file_sha256"]) for r in rows if r["file_sha256"]]

    def fetch_chunk_ids(self, *, doc_id: str, version_id: str | None = None) -> list[str]:
        if version_id:
            sql = "SELECT chunk_id FROM chunks WHERE doc_id=? AND version_id=?"
            params = (doc_id, version_id)
        else:
            sql = "SELECT chunk_id FROM chunks WHERE doc_id=?"
            params = (doc_id,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [str(r["chunk_id"]) for r in rows]

    def fetch_asset_ids_by_doc_version(self, *, doc_id: str, version_id: str | None = None) -> list[str]:
        if version_id:
            sql = "SELECT DISTINCT asset_id FROM asset_refs WHERE doc_id=? AND version_id=?"
            params = (doc_id, version_id)
        else:
            sql = "SELECT DISTINCT asset_id FROM asset_refs WHERE doc_id=?"
            params = (doc_id,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [str(r["asset_id"]) for r in rows if r["asset_id"]]

    def delete_chunk_assets(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        placeholders = ",".join(["?"] * len(chunk_ids))
        sql = f"DELETE FROM chunk_assets WHERE chunk_id IN ({placeholders})"
        with self._connect() as conn:
            cur = conn.execute(sql, tuple(chunk_ids))
        return int(cur.rowcount or 0)

    def delete_chunks(self, *, doc_id: str, version_id: str | None = None) -> int:
        if version_id:
            sql = "DELETE FROM chunks WHERE doc_id=? AND version_id=?"
            params = (doc_id, version_id)
        else:
            sql = "DELETE FROM chunks WHERE doc_id=?"
            params = (doc_id,)
        with self._connect() as conn:
            cur = conn.execute(sql, params)
        return int(cur.rowcount or 0)

    def delete_asset_refs(self, *, doc_id: str, version_id: str | None = None) -> int:
        if version_id:
            sql = "DELETE FROM asset_refs WHERE doc_id=? AND version_id=?"
            params = (doc_id, version_id)
        else:
            sql = "DELETE FROM asset_refs WHERE doc_id=?"
            params = (doc_id,)
        with self._connect() as conn:
            cur = conn.execute(sql, params)
        return int(cur.rowcount or 0)

    def count_asset_refs(self, asset_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM asset_refs WHERE asset_id=?",
                (asset_id,),
            ).fetchone()
        return int(row["c"] if row else 0)

    def delete_assets(self, asset_ids: list[str]) -> int:
        if not asset_ids:
            return 0
        placeholders = ",".join(["?"] * len(asset_ids))
        sql = f"DELETE FROM assets WHERE asset_id IN ({placeholders})"
        with self._connect() as conn:
            cur = conn.execute(sql, tuple(asset_ids))
        return int(cur.rowcount or 0)

    def delete_doc_versions(self, *, doc_id: str, version_id: str | None = None) -> int:
        if version_id:
            sql = "DELETE FROM doc_versions WHERE doc_id=? AND version_id=?"
            params = (doc_id, version_id)
        else:
            sql = "DELETE FROM doc_versions WHERE doc_id=?"
            params = (doc_id,)
        with self._connect() as conn:
            cur = conn.execute(sql, params)
        return int(cur.rowcount or 0)

    def delete_document_if_orphan(self, doc_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM doc_versions WHERE doc_id=?", (doc_id,)).fetchone()
            cnt = int(row["c"] if row else 0)
            if cnt == 0:
                cur = conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
                return int(cur.rowcount or 0)
        return 0


def new_doc_id() -> str:
    return f"doc_{uuid.uuid4().hex}"


def new_version_id() -> str:
    return f"ver_{uuid.uuid4().hex}"
