from __future__ import annotations

from src.observability.trace.envelope import EventRecord, SpanRecord, TraceEnvelope, compute_aggregates


def test_compute_aggregates_from_spans_and_events() -> None:
    span = SpanRecord(
        span_id="s1",
        name="stage.retrieve_dense",
        parent_span_id=None,
        start_ts=0.0,
        end_ts=1.0,
    )
    span.events.append(EventRecord(ts=0.5, kind="retrieval.candidates", attrs={"source": "dense", "count": 3}))
    span.events.append(EventRecord(ts=0.6, kind="retrieval.fused", attrs={"count": 2}))

    env = TraceEnvelope(
        trace_id="t-agg",
        trace_type="query",
        status="ok",
        start_ts=0.0,
        end_ts=2.0,
        strategy_config_id="scfg_test",
        spans=[span],
        events=[],
        aggregates={},
    )

    agg = compute_aggregates(env)
    assert agg["latency_ms"] == 2000.0
    assert agg["stage_latency_ms"]["stage.retrieve_dense"] == 1000.0
    assert agg["counters"]["retrieval.candidates.dense"] == 3
    assert agg["counters"]["retrieval.fused"] == 2
