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
def test_mcp_library_query_after_ingest_over_stdio(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir)

    md_path = tmp_path / "doc.md"
    md_path.write_text("# Title\n\nhello world from chunk\n", encoding="utf-8")

    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)

    cmd = [sys.executable, "-m", "src.mcp_server._test_mcp_ingest_query_entrypoint"]
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
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "library.query", "arguments": {"query": "hello world", "top_k": 3}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    p.stdin.flush()
    p.stdin.close()

    out1 = json.loads(p.stdout.readline().strip())
    assert out1["id"] == 1
    st1 = out1["result"]["structuredContent"]["structured"]
    assert st1["status"] in {"ok", "skipped"}
    doc_id = st1["doc_id"]
    version_id = st1["version_id"]

    out2 = json.loads(p.stdout.readline().strip())
    assert out2["id"] == 2
    res2 = out2["result"]
    assert res2["content"][0]["type"] == "text"
    assert "Retrieved Chunks" in res2["content"][0]["text"] or "未召回到相关内容" in res2["content"][0]["text"]

    sc2 = res2.get("structuredContent")
    assert isinstance(sc2, dict)
    sources = sc2.get("sources")
    assert isinstance(sources, list)

    # If there are sources, they should resolve back to the same doc/version we ingested.
    if sources:
        s0 = sources[0]
        assert s0.get("doc_id") == doc_id
        assert s0.get("version_id") == version_id

    # Verify sqlite has chunks for the ingested doc/version (sanity).
    app_db = data_dir / "sqlite" / "app.sqlite"
    with sqlite3.connect(app_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM chunks WHERE doc_id=? AND version_id=?",
            (doc_id, version_id),
        ).fetchone()
    assert row is not None and int(row["c"]) > 0

    p.terminate()

