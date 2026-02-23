from __future__ import annotations

from pathlib import Path


def test_unit_sentinel_file_written() -> None:
    """
    This test intentionally produces a side-effect in a controlled location
    so other tests can verify marker-based selection.
    """
    root = Path(__file__).resolve().parents[2]
    sentinel = root / "cache" / "_unit_ran"
    sentinel.write_text("1", encoding="utf-8")

