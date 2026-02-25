from __future__ import annotations

from src.core.strategy import build_runtime_from_strategy


def test_provider_swap_changes_output() -> None:
    rt_a = build_runtime_from_strategy("local.default")
    rt_b = build_runtime_from_strategy("local.alt")

    a_provider, _ = rt_a.strategy.resolve_provider("embedder")
    b_provider, _ = rt_b.strategy.resolve_provider("embedder")
    assert a_provider != b_provider

    v1 = rt_a.embedder.embed_texts(["hello"])[0]
    v2 = rt_b.embedder.embed_texts(["hello"])[0]
    assert v1 != v2

    r1 = rt_a.llm.generate("answer", [{"role": "user", "content": "hi"}]).text
    r2 = rt_b.llm.generate("answer", [{"role": "user", "content": "hi"}]).text
    assert r1 != r2
