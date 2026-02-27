from __future__ import annotations

import json
import subprocess
import sys

import pytest


@pytest.mark.integration
def test_stdio_transport_subprocess_roundtrip() -> None:
    # Start the minimal stdio server and send one JSON-RPC request, then close stdin.
    cmd = [sys.executable, "-m", "src.mcp_server._test_entrypoint"]
    p = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert p.stdin is not None and p.stdout is not None

    p.stdin.write('{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":1}}\n')
    p.stdin.flush()
    p.stdin.close()

    line = p.stdout.readline().strip()
    obj = json.loads(line)
    assert obj["jsonrpc"] == "2.0"
    assert obj["id"] == 1
    assert obj["result"]["ok"] is True
    assert obj["result"]["params"] == {"x": 1}

    p.terminate()

