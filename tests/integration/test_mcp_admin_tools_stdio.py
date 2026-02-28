from __future__ import annotations

import json
import os
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
def test_mcp_list_delete_affects_query_soft_delete(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir)

    md_path = tmp_path / "doc.md"
    md_path.write_text("# Title\n\nhello world from chunk\n", encoding="utf-8")

    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)

    repo_root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "src.mcp_server._test_mcp_admin_entrypoint"]
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(repo_root),
    )
    assert p.stdin is not None and p.stdout is not None

    # 1) ingest
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
    # 2) list_documents should include the version (not deleted)
    p.stdin.write(
        json.dumps(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "library.list_documents", "arguments": {}}},
            ensure_ascii=False,
        )
        + "\n"
    )
    p.stdin.flush()

    out1 = json.loads(p.stdout.readline().strip())
    st1 = out1["result"]["structuredContent"]["structured"]
    doc_id = st1["doc_id"]
    version_id = st1["version_id"]

    out2 = json.loads(p.stdout.readline().strip())
    items = out2["result"]["structuredContent"]["structured"]["items"]
    assert any(it["doc_id"] == doc_id and it["version_id"] == version_id and it["status"] != "deleted" for it in items)

    # 3) delete version (soft)
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "library.delete_document", "arguments": {"doc_id": doc_id, "version_id": version_id}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    # 4) query should not return deleted sources (context stage drops them)
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "library.query", "arguments": {"query": "hello world", "top_k": 3}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    # 5) list_documents default should exclude deleted
    p.stdin.write(
        json.dumps(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "library.list_documents", "arguments": {}}},
            ensure_ascii=False,
        )
        + "\n"
    )
    # 6) list_documents include_deleted=true should include deleted
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "library.list_documents", "arguments": {"include_deleted": True}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    p.stdin.flush()
    p.stdin.close()

    out3 = json.loads(p.stdout.readline().strip())
    assert out3["id"] == 3
    assert out3["result"]["structuredContent"]["structured"]["status"] in {"ok", "noop"}

    out4 = json.loads(p.stdout.readline().strip())
    assert out4["id"] == 4
    sources = out4["result"]["structuredContent"].get("sources") or []
    # No sources should belong to the deleted version.
    assert all(s.get("version_id") != version_id for s in sources)

    out5 = json.loads(p.stdout.readline().strip())
    items5 = out5["result"]["structuredContent"]["structured"]["items"]
    assert not any(it["version_id"] == version_id and it["status"] == "deleted" for it in items5)

    out6 = json.loads(p.stdout.readline().strip())
    items6 = out6["result"]["structuredContent"]["structured"]["items"]
    assert any(it["version_id"] == version_id and it["status"] == "deleted" for it in items6)

    p.terminate()

