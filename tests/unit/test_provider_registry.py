from __future__ import annotations

import pytest

from src.libs.registry import (
    ProviderAlreadyRegisteredError,
    ProviderNotFoundError,
    ProviderRegistry,
)


class DummyProvider:
    def __init__(self, x: int = 1, y: str | None = None) -> None:
        self.x = x
        self.y = y


def test_register_get_create_success() -> None:
    reg = ProviderRegistry()
    reg.register("embedder", "fake", DummyProvider)

    assert reg.has("embedder", "fake")
    ctor = reg.get("embedder", "fake")
    inst = ctor(x=2, y="ok")
    assert isinstance(inst, DummyProvider)
    assert inst.x == 2
    assert inst.y == "ok"

    inst2 = reg.create("embedder", "fake", x=3)
    assert isinstance(inst2, DummyProvider)
    assert inst2.x == 3


def test_register_duplicate_rejected() -> None:
    reg = ProviderRegistry()
    reg.register("loader", "md", DummyProvider)
    with pytest.raises(ProviderAlreadyRegisteredError):
        reg.register("loader", "md", DummyProvider)


def test_missing_provider_raises() -> None:
    reg = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        reg.get("llm", "missing")
    with pytest.raises(ProviderNotFoundError):
        reg.create("llm", "missing")


def test_register_invalid_inputs() -> None:
    reg = ProviderRegistry()
    with pytest.raises(ValueError):
        reg.register("", "x", DummyProvider)
    with pytest.raises(ValueError):
        reg.register("x", "", DummyProvider)
    with pytest.raises(TypeError):
        reg.register("x", "y", None)  # type: ignore[arg-type]

