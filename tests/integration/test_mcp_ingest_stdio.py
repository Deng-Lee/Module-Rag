from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


def _write_settings_yaml(p: Path, *, data_dir: Path) -> None:
    raw = "\n".join(
        [
            "paths:",
            f"  data_dir: {data_dir.as_posix()}",
            f"  raw_dir: {(data_dir / 'raw').as_posix()}",
            f"  md_dir: {(data_dir / 'md').as_posix()}",
            f"  assets_dir: {(data_dir / 'assets').as_posix()}",
            f"  chroma_dir: {(data_dir / 'chroma').as_posix()}",
            f"  sqlite_dir: {(data_dir / 'sqlite').as_posix()}",
            "  cache_dir: cache",
            "  logs_dir: logs",
            "",
            "defaults:",
            "  strategy_config_id: local.default",
            "",
        ]
    )
    p.write_text(raw, encoding="utf-8")


@pytest.mark.integration
def test_mcp_library_ingest_over_stdio_persists_stores(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir)

    md_path = tmp_path / "doc.md"
    md_path.write_text("# Title\n\nhello world from chunk\n", encoding="utf-8")

    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)

    cmd = [sys.executable, "-m", "src.mcp_server._test_mcp_ingest_entrypoint"]
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert p.stdin is not None and p.stdout is not None

    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "library.ingest", "arguments": {"file_path": str(md_path)}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    p.stdin.flush()
    p.stdin.close()

    out = json.loads(p.stdout.readline().strip())
    assert out["id"] == 1
    result = out["result"]
    assert result["content"][0]["type"] == "text"
    sc = result.get("structuredContent")
    assert isinstance(sc, dict)
    structured = sc.get("structured")
    assert isinstance(structured, dict)
    assert structured.get("status") in {"ok", "skipped"}

    doc_id = structured.get("doc_id")
    version_id = structured.get("version_id")
    assert isinstance(doc_id, str) and doc_id
    assert isinstance(version_id, str) and version_id

    # FS: md_norm persisted
    md_norm_path = data_dir / "md" / doc_id / version_id / "md_norm.md"
    assert md_norm_path.exists()

    # SQLite: chunks persisted
    app_db = data_dir / "sqlite" / "app.sqlite"
    assert app_db.exists()
    with sqlite3.connect(app_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM chunks WHERE doc_id=? AND version_id=?",
            (doc_id, version_id),
        ).fetchone()
    assert row is not None and int(row["c"]) > 0

    # ChromaLite: vectors persisted
    chroma_db = data_dir / "chroma" / "chroma_lite.sqlite"
    assert chroma_db.exists()
    with sqlite3.connect(chroma_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT COUNT(*) AS c FROM vectors").fetchone()
    assert row is not None and int(row["c"]) > 0

    p.terminate()

