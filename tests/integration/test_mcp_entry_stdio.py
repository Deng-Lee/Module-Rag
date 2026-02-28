from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _write_settings_yaml(p: Path, *, data_dir: Path, logs_dir: Path) -> None:
    raw = "\n".join(
        [
            "paths:",
            f"  data_dir: {data_dir.as_posix()}",
            f"  raw_dir: {(data_dir / 'raw').as_posix()}",
            f"  md_dir: {(data_dir / 'md').as_posix()}",
            f"  assets_dir: {(data_dir / 'assets').as_posix()}",
            f"  chroma_dir: {(data_dir / 'chroma').as_posix()}",
            f"  sqlite_dir: {(data_dir / 'sqlite').as_posix()}",
            f"  logs_dir: {logs_dir.as_posix()}",
            "  cache_dir: cache",
            "",
            "defaults:",
            "  strategy_config_id: local.default",
            "",
        ]
    )
    p.write_text(raw, encoding="utf-8")


@pytest.mark.integration
def test_mcp_entry_stdio_writes_trace_jsonl(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir, logs_dir=logs_dir)

    md_path = tmp_path / "doc.md"
    md_path.write_text("# Title\n\nhello world from chunk\n", encoding="utf-8")

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

    # 1) tools/list sanity
    p.stdin.write('{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n')
    # 2) ingest to generate a trace
    p.stdin.write(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "library.ingest", "arguments": {"file_path": str(md_path)}},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    p.stdin.flush()
    p.stdin.close()

    out1 = json.loads(p.stdout.readline().strip())
    assert out1["id"] == 1
    names = [t["name"] for t in out1["result"]["tools"]]
    assert "library.ingest" in names

    out2 = json.loads(p.stdout.readline().strip())
    assert out2["id"] == 2
    assert out2["result"]["structuredContent"]["structured"]["status"] in {"ok", "skipped"}

    # A trace line should be written to logs/traces.jsonl
    trace_path = logs_dir / "traces.jsonl"
    assert trace_path.exists()
    assert trace_path.read_text(encoding="utf-8").strip() != ""

    p.terminate()

