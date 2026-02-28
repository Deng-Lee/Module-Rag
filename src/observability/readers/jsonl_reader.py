from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from ..trace.envelope import EventRecord, SpanRecord, TraceEnvelope


def _event_from_dict(d: dict[str, Any]) -> EventRecord:
    return EventRecord(ts=float(d["ts"]), kind=str(d["kind"]), attrs=dict(d.get("attrs", {})))


def _span_from_dict(d: dict[str, Any]) -> SpanRecord:
    events = [_event_from_dict(e) for e in d.get("events", [])]
    return SpanRecord(
        span_id=str(d["span_id"]),
        name=str(d["name"]),
        parent_span_id=d.get("parent_span_id"),
        start_ts=float(d["start_ts"]),
        end_ts=float(d["end_ts"]) if d.get("end_ts") is not None else None,
        status=str(d.get("status", "ok")),
        attrs=dict(d.get("attrs", {})),
        events=events,
    )


def _envelope_from_dict(d: dict[str, Any]) -> TraceEnvelope:
    spans = [_span_from_dict(s) for s in d.get("spans", [])]
    events = [_event_from_dict(e) for e in d.get("events", [])]
    return TraceEnvelope(
        schema_version=str(d.get("schema_version", "trace.v1")),
        trace_id=str(d["trace_id"]),
        trace_type=str(d.get("trace_type", "unknown")),
        status=str(d.get("status", "ok")),
        start_ts=float(d["start_ts"]),
        end_ts=float(d["end_ts"]),
        strategy_config_id=str(d.get("strategy_config_id", "unknown")),
        spans=spans,
        events=events,
        aggregates=dict(d.get("aggregates", {})),
        providers=dict(d.get("providers", {})),
    )


class JsonlReader:
    def __init__(self, path_or_dir: str | Path) -> None:
        p = Path(path_or_dir)
        if p.suffix == ".jsonl":
            self.path = p
        elif p.is_dir() or str(path_or_dir).endswith(("/", "\\")):
            self.path = p / "traces.jsonl"
        else:
            self.path = p / "traces.jsonl"

    def iter_traces(self) -> Iterator[TraceEnvelope]:
        if not self.path.exists():
            return iter(())
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                yield _envelope_from_dict(data)
