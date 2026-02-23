from __future__ import annotations

import json
from pathlib import Path

from src.observability.readers.jsonl_reader import JsonlReader
from src.observability.sinks.jsonl import JsonlSink
from src.observability.trace.context import TraceContext


def _make_envelope(trace_id: str) -> object:
    ctx = TraceContext.new(trace_id)
    with TraceContext.activate(ctx):
        with ctx.start_span("stage.test"):
            ctx.add_event("evt", {"x": 1})
        return ctx.finish()


def test_jsonl_sink_write_and_append(tmp_path: Path) -> None:
    path = tmp_path / "traces.jsonl"
    sink = JsonlSink(path)

    env1 = _make_envelope("t-1")
    env2 = _make_envelope("t-2")
    sink.write(env1)
    sink.write(env2)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    rec = json.loads(lines[0])
    assert rec["trace_id"] == "t-1"
    assert "spans" in rec
    assert "events" in rec
    assert "start_ts" in rec and "end_ts" in rec


def test_jsonl_reader_iter_traces(tmp_path: Path) -> None:
    path = tmp_path / "traces.jsonl"
    sink = JsonlSink(path)

    env1 = _make_envelope("t-3")
    sink.write(env1)

    reader = JsonlReader(path)
    traces = list(reader.iter_traces())
    assert len(traces) == 1
    assert traces[0].trace_id == "t-3"

