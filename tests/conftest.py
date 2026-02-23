from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Provide an isolated working directory for tests that write to disk using
    relative paths.
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def mock_clock(monkeypatch: pytest.MonkeyPatch) -> float:
    """
    Freeze time.time() to a deterministic value.

    A-2 scope: keep it minimal; later stages can extend to datetime/timezone.
    """
    import time

    fixed = 1_700_000_000.0
    monkeypatch.setattr(time, "time", lambda: fixed)
    return fixed


# Prefer pytest-mock's "mocker" fixture when installed; otherwise provide
# a tiny compatible subset so unit tests can still run in constrained envs.
try:  # pragma: no cover
    import pytest_mock as _pytest_mock  # noqa: F401
except Exception:  # pragma: no cover

    @dataclass
    class _MiniMocker:
        _patchers: list[Any]

        def patch(self, target: str, *args: Any, **kwargs: Any) -> Any:
            from unittest.mock import patch

            p = patch(target, *args, **kwargs)
            self._patchers.append(p)
            return p.start()

        def stopall(self) -> None:
            for p in reversed(self._patchers):
                try:
                    p.stop()
                except Exception:
                    pass
            self._patchers.clear()

    @pytest.fixture
    def mocker() -> Generator[_MiniMocker, None, None]:
        m = _MiniMocker(_patchers=[])
        try:
            yield m
        finally:
            m.stopall()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """
    Default behavior: only run unit tests.

    If the user explicitly provides `-m ...`, we respect it and do not apply
    any extra deselection logic.
    """
    if config.option.markexpr:
        return

    deselect: list[pytest.Item] = []
    keep: list[pytest.Item] = []

    for item in items:
        if item.get_closest_marker("integration") or item.get_closest_marker("e2e"):
            deselect.append(item)
        else:
            keep.append(item)

    if deselect:
        config.hook.pytest_deselected(items=deselect)
        items[:] = keep

