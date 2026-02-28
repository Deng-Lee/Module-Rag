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
def test_mcp_query_assets_and_get_document_over_stdio(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir)

    # Build a markdown that references a local image.
    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
    img_src = fixtures_dir / "assets" / "sample.svg"
    img_path = tmp_path / "sample.svg"
    img_path.write_bytes(img_src.read_bytes())

    md_path = tmp_path / "doc.md"
    md_path.write_text(f"# Title\n\nHere is an image: ![alt]({img_path.as_posix()})\n", encoding="utf-8")

    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)

    repo_root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "src.mcp_server._test_mcp_assets_entrypoint"]
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
    # 2) query (get asset_ids from sources)
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "library.query", "arguments": {"query": "image", "top_k": 3}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    p.stdin.flush()

    out1 = json.loads(p.stdout.readline().strip())
    assert out1["id"] == 1
    st1 = out1["result"]["structuredContent"]["structured"]
    assert st1["status"] in {"ok", "skipped"}
    doc_id = st1["doc_id"]
    version_id = st1["version_id"]

    out2 = json.loads(p.stdout.readline().strip())
    assert out2["id"] == 2
    sc2 = out2["result"]["structuredContent"]
    sources = sc2.get("sources") or []
    assert isinstance(sources, list)
    # Find any asset_ids from sources.
    asset_ids: list[str] = []
    for s in sources:
        aids = s.get("asset_ids")
        if isinstance(aids, list):
            asset_ids.extend([x for x in aids if isinstance(x, str) and x])
    assert asset_ids, "expected at least one asset_id in retrieved sources"

    # 3) query_assets
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "library.query_assets", "arguments": {"asset_ids": asset_ids, "max_bytes": 200000}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    # 4) get_document
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "library.get_document",
                    "arguments": {"doc_id": doc_id, "version_id": version_id, "max_chars": 20000},
                },
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    p.stdin.flush()
    p.stdin.close()

    out3 = json.loads(p.stdout.readline().strip())
    assert out3["id"] == 3
    res3 = out3["result"]["structuredContent"]["structured"]
    assets = res3.get("assets")
    assert isinstance(assets, list) and assets
    assert "bytes_b64" in assets[0]

    out4 = json.loads(p.stdout.readline().strip())
    assert out4["id"] == 4
    text = out4["result"]["content"][0]["text"]
    assert "asset://" in text  # image link is normalized

    p.terminate()
