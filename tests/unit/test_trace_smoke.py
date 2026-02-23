from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.observability.obs import api as obs
from src.observability.sinks.jsonl import JsonlSink
from src.observability.trace.context import TraceContext


def _validate_min_schema(record: dict[str, Any]) -> None:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "observability"
        / "schema"
        / "trace_envelope.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    for key in schema.get("required", []):
        assert key in record


def run_trace_smoke(log_dir: Path) -> str:
    sink = JsonlSink(log_dir)
    ctx = TraceContext.new("trace_smoke")

    with TraceContext.activate(ctx):
        with obs.span("stage.smoke"):
            obs.event("smoke.event", {"x": 1})
            obs.metric("smoke.metric", 1)
        env = ctx.finish()
        sink.on_trace_end(env)

    return env.trace_id


def test_trace_smoke_jsonl_roundtrip(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    trace_id = run_trace_smoke(log_dir)
    assert trace_id == "trace_smoke"

    path = log_dir / "traces.jsonl"
    assert path.exists()

    line = path.read_text(encoding="utf-8").strip()
    record = json.loads(line)

    _validate_min_schema(record)
    assert record["trace_id"] == "trace_smoke"
    assert isinstance(record["spans"], list)
    assert len(record["spans"]) == 1
    assert isinstance(record["events"], list)

