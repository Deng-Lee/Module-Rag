# ruff: noqa: E402, I001
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = (
    Path(__file__).resolve().parents[2] / "skills" / "qa-test-plus" / "scripts"
).resolve()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from qa_plus_common import is_retryable_error, retry_call


def test_retry_call_retries_timeout_then_succeeds() -> None:
    calls = {"count": 0}

    def flaky() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            raise TimeoutError("Request timed out.")
        return "ok"

    result, attempts = retry_call(flaky, operation="unit.retry", attempts=3, backoff_s=0.0)
    assert result == "ok"
    assert attempts == 3


def test_is_retryable_error_skips_fault_injection_endpoint() -> None:
    exc = subprocess.CalledProcessError(
        1,
        ["bash", "scripts/dev_query.sh"],
        stderr="httpx.ConnectError: [Errno 61] Connection refused for http://127.0.0.1:9/v1",
    )
    assert is_retryable_error(exc) is False
