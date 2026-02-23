from __future__ import annotations

import pytest

from src.observability.trace.context import TraceContext


def test_trace_context_activate_and_current() -> None:
    assert TraceContext.current() is None

    ctx = TraceContext.new("t1")
    with TraceContext.activate(ctx):
        assert TraceContext.current() is ctx
    assert TraceContext.current() is None


def test_nested_spans_parent_child_relationship(mock_clock) -> None:
    ctx = TraceContext.new("t2")
    with TraceContext.activate(ctx):
        with ctx.start_span("outer"):
            ctx.add_event("outer.ev")
            with ctx.start_span("inner", {"k": "v"}):
                ctx.add_event("inner.ev", {"x": 1})
        env = ctx.finish()

    assert env.trace_id == "t2"
    assert len(env.spans) == 2
    outer, inner = env.spans[0], env.spans[1]
    assert outer.name == "outer"
    assert inner.name == "inner"
    assert inner.parent_span_id == outer.span_id
    assert outer.end_ts is not None and inner.end_ts is not None
    assert [e.kind for e in outer.events] == ["outer.ev"]
    assert [e.kind for e in inner.events] == ["inner.ev"]


def test_exception_records_error_and_finish_is_still_possible() -> None:
    ctx = TraceContext.new("t3")
    with TraceContext.activate(ctx):
        with pytest.raises(ValueError):
            with ctx.start_span("boom"):
                raise ValueError("bad")
        env = ctx.finish()

    assert len(env.spans) == 1
    s = env.spans[0]
    assert s.status == "error"
    assert s.end_ts is not None
    assert any(e.kind == "error" for e in s.events)

