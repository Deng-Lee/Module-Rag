from __future__ import annotations

import pytest

from src.observability.obs import api as obs
from src.observability.trace.context import TraceContext


def test_trace_envelope_validate_rejects_invalid_event_kind() -> None:
    ctx = TraceContext.new("t-validate-1", trace_type="query", strategy_config_id="scfg_test")
    with TraceContext.activate(ctx):
        with obs.span("stage.test"):
            obs.event("invalid.kind", {"x": 1})
        env = ctx.finish()

    with pytest.raises(ValueError):
        env.validate(strict=True)


def test_trace_envelope_validate_accepts_allowed_event_kind() -> None:
    ctx = TraceContext.new("t-validate-2", trace_type="query", strategy_config_id="scfg_test")
    with TraceContext.activate(ctx):
        with obs.span("stage.test"):
            obs.event("retrieval.candidates", {"count": 0})
        env = ctx.finish()

    env.validate(strict=True)
