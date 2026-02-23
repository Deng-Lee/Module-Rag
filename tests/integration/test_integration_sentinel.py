from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.integration
def test_integration_sentinel_file_written() -> None:
    root = Path(__file__).resolve().parents[2]
    sentinel = root / "cache" / "_integration_ran"
    sentinel.write_text("1", encoding="utf-8")

