from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_pytest(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_runs_unit_only_and_integration_is_opt_in() -> None:
    """
    Black-box verification for A-2:
    - default run deselects integration tests
    - `-m integration` runs integration tests and does not run unit tests
    """
    root = Path(__file__).resolve().parents[2]
    unit_sentinel = root / "cache" / "_unit_ran"
    integration_sentinel = root / "cache" / "_integration_ran"

    unit_sentinel.unlink(missing_ok=True)
    integration_sentinel.unlink(missing_ok=True)

    # Default: unit runs, integration does not.
    r1 = _run_pytest(
        [
            "-q",
            "tests/unit/test_unit_sentinel.py",
            "tests/integration/test_integration_sentinel.py",
        ]
    )
    assert r1.returncode == 0, (r1.stdout, r1.stderr)
    assert unit_sentinel.exists()
    assert not integration_sentinel.exists()

    unit_sentinel.unlink(missing_ok=True)
    integration_sentinel.unlink(missing_ok=True)

    # Opt-in: integration runs; unit should not be selected by `-m integration`.
    r2 = _run_pytest(
        [
            "-q",
            "-m",
            "integration",
            "tests/unit/test_unit_sentinel.py",
            "tests/integration/test_integration_sentinel.py",
        ]
    )
    assert r2.returncode == 0, (r2.stdout, r2.stderr)
    assert not unit_sentinel.exists()
    assert integration_sentinel.exists()

