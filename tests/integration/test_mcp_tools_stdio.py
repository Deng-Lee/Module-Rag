from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.mark.integration
def test_mcp_tools_list_and_call_over_stdio() -> None:
    cmd = [sys.executable, "-m", "src.mcp_server._test_mcp_entrypoint"]
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
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

    p.terminate()

