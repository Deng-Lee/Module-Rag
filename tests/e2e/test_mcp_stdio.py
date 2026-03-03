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
            "  strategy_config_id: local.test",
            "",
            "eval:",
            "  datasets_dir: tests/datasets",
            "",
        ]
    )
    p.write_text(raw, encoding="utf-8")


def _write_png(path: Path) -> None:
    # 1x1 PNG
    png_bytes = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000A49444154789C6360000002000154010D0A0000000049454E44AE426082"
    )
    path.write_bytes(png_bytes)


def _spawn_server(settings_path: Path) -> subprocess.Popen[str]:
    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    repo_root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "src.mcp_server.entry"]
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
    return p


def _jsonrpc_call(p: subprocess.Popen[str], req: dict) -> dict:
    assert p.stdin is not None and p.stdout is not None
    p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
    p.stdin.flush()
    line = p.stdout.readline().strip()
    return json.loads(line)


@pytest.mark.e2e
def test_mcp_stdio_full_tools(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir)

    img_path = tmp_path / "img.png"
    _write_png(img_path)

    md_path = tmp_path / "doc.md"
    md_path.write_text(
        f"# Title\n\nhello world with image ![img]({img_path.as_posix()})\n",
        encoding="utf-8",
    )

    p = _spawn_server(settings_path)

    try:
        # tools/list
        out = _jsonrpc_call(
            p,
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        tools = out["result"]["tools"]
        names = {t.get("name") for t in tools}
        assert {
            "library_ingest",
            "library_query",
            "library_query_assets",
            "library_get_document",
            "library_list_documents",
            "library_delete_document",
            "library_ping",
        }.issubset(names)

        # ingest
        out = _jsonrpc_call(
            p,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "library_ingest", "arguments": {"file_path": str(md_path)}},
            },
        )
        structured = out["result"]["structuredContent"]["structured"]
        assert structured["status"] in {"ok", "skipped"}
        doc_id = structured["doc_id"]
        version_id = structured["version_id"]

        # query
        out = _jsonrpc_call(
            p,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "library_query", "arguments": {"query": "hello world", "top_k": 3}},
            },
        )
        sc = out["result"]["structuredContent"]
        sources = sc.get("sources") or []
        assert isinstance(sources, list)
        asset_ids: list[str] = []
        for s in sources:
            for aid in s.get("asset_ids", []) or []:
                asset_ids.append(aid)
        assert asset_ids, "expected asset_ids in sources"

        # query_assets
        out = _jsonrpc_call(
            p,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "library_query_assets", "arguments": {"asset_ids": asset_ids[:1]}},
            },
        )
        assets = out["result"]["structuredContent"]["structured"]["assets"]
        assert assets and assets[0]["asset_id"] == asset_ids[0]

        # get_document
        out = _jsonrpc_call(
            p,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "library_get_document",
                    "arguments": {"doc_id": doc_id, "version_id": version_id},
                },
            },
        )
        assert out["result"]["content"][0]["type"] == "text"

        # list_documents
        out = _jsonrpc_call(
            p,
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "library_list_documents", "arguments": {"include_deleted": True}},
            },
        )
        items = out["result"]["structuredContent"]["structured"]["items"]
        assert any(it["doc_id"] == doc_id for it in items)

        # delete_document (soft)
        out = _jsonrpc_call(
            p,
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {"name": "library_delete_document", "arguments": {"doc_id": doc_id}},
            },
        )
        assert out["result"]["structuredContent"]["structured"]["status"] in {"ok", "noop"}

        # query again should drop deleted chunks
        out = _jsonrpc_call(
            p,
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {"name": "library_query", "arguments": {"query": "hello world", "top_k": 3}},
            },
        )
        sc = out["result"].get("structuredContent", {})
        sources = sc.get("sources") or []
        assert sources == []
    finally:
        if p.stdin:
            try:
                p.stdin.close()
            except Exception:
                pass
        p.terminate()
