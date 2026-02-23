from __future__ import annotations

from dataclasses import dataclass, field

from src.observability.obs import api as obs
from src.observability.trace.context import TraceContext
from src.observability.trace.envelope import TraceEnvelope


@dataclass
class FakeSink:
    events: list[dict] = field(default_factory=list)
    metrics: list[dict] = field(default_factory=list)
    span_ends: list[dict] = field(default_factory=list)
    trace_ends: list[TraceEnvelope] = field(default_factory=list)

    def on_event(self, record: dict) -> None:
        self.events.append(record)

    def on_metric(self, record: dict) -> None:
        self.metrics.append(record)

    def on_span_end(self, record: dict) -> None:
        self.span_ends.append(record)

    def on_trace_end(self, envelope: TraceEnvelope) -> None:
        self.trace_ends.append(envelope)


def test_obs_api_no_sink_no_crash() -> None:
    ctx = TraceContext.new("t-obs-1")
    with TraceContext.activate(ctx):
        with obs.span("stage.test"):
            obs.event("k1", {"x": 1})
            obs.metric("latency_ms", 12.3, {"unit": "ms"})
        env = ctx.finish()

    assert env.trace_id == "t-obs-1"
    assert len(env.spans) == 1
    assert any(e.kind == "k1" for e in env.spans[0].events)
    assert any(e.kind == "metric" for e in env.spans[0].events)


def test_obs_api_with_sink_captures_records() -> None:
    sink = FakeSink()
    obs.set_sink(sink)
    try:
        ctx = TraceContext.new("t-obs-2")
        with TraceContext.activate(ctx):
            with obs.span("stage.test", {"p": "v"}):
                obs.event("evt.ok", {"a": 1})
                obs.metric("count", 1)
            env = ctx.finish()
            sink.on_trace_end(env)
    finally:
        obs.set_sink(None)

    assert len(sink.span_ends) == 1
    assert sink.span_ends[0]["name"] == "stage.test"
    assert sink.span_ends[0]["trace_id"] == "t-obs-2"
    assert len(sink.events) == 1
    assert sink.events[0]["kind"] == "evt.ok"
    assert sink.events[0]["trace_id"] == "t-obs-2"
    assert len(sink.metrics) == 1
    assert sink.metrics[0]["name"] == "count"
    assert sink.metrics[0]["trace_id"] == "t-obs-2"

