from __future__ import annotations

import pytest

from src.observability.obs import api as obs
from src.observability.trace.context import TraceContext


def _kinds(env) -> list[str]:
    kinds: list[str] = []
    for s in env.spans:
        kinds.extend([e.kind for e in s.events])
    return kinds


def test_with_stage_emits_start_and_end() -> None:
    ctx = TraceContext.new("t-stage-1", trace_type="query", strategy_config_id="scfg_test")
    with TraceContext.activate(ctx):
        with obs.with_stage("loader"):
            obs.event("retrieval.candidates", {"count": 0})
        env = ctx.finish()

    assert [s.name for s in env.spans] == ["stage.loader"]
    kinds = _kinds(env)
    assert "stage.start" in kinds
    assert "stage.end" in kinds
    assert "retrieval.candidates" in kinds


def test_with_stage_emits_error_on_exception() -> None:
    ctx = TraceContext.new("t-stage-2", trace_type="query", strategy_config_id="scfg_test")
    with TraceContext.activate(ctx):
        with pytest.raises(ValueError):
            with obs.with_stage("boom"):
                raise ValueError("bad")
        env = ctx.finish()

    span = env.spans[0]
    assert span.name == "stage.boom"
    assert span.status == "error"
    kinds = _kinds(env)
    assert "stage.error" in kinds
