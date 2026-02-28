from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_mcp_tools_list_and_call_over_stdio() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "src.mcp_server._test_mcp_entrypoint"]
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(repo_root),
    )
    assert p.stdin is not None and p.stdout is not None

    p.stdin.write('{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n')
    p.stdin.write(
        '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"library.ping","arguments":{"message":"hi"}}}\n'
    )
    p.stdin.flush()
    p.stdin.close()

    out1 = json.loads(p.stdout.readline().strip())
    assert out1["id"] == 1
    names = [t["name"] for t in out1["result"]["tools"]]
    assert "library.ping" in names

    out2 = json.loads(p.stdout.readline().strip())
    assert out2["id"] == 2
    assert out2["result"]["content"][0]["type"] == "text"
    assert "hi" in out2["result"]["content"][0]["text"]

    # E-8: deadline parameter should be accepted and return a structured error.
    # We use timeout_ms=0 to ensure it trips before tool execution.
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(repo_root),
    )
    assert p.stdin is not None and p.stdout is not None
    p.stdin.write(
        '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"library.ping","arguments":{"message":"hi"},"timeout_ms":0}}\n'
    )
    p.stdin.flush()
    p.stdin.close()
    out3 = json.loads(p.stdout.readline().strip())
    assert out3["id"] == 3
    assert out3["error"]["code"] == -32001
    assert "trace_id" in (out3["error"].get("data") or {})
    p.terminate()

    p.terminate()
