from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class EventRecord:
    ts: float
    kind: str
    attrs: JsonDict = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        return {"ts": self.ts, "kind": self.kind, "attrs": self.attrs}


@dataclass
class SpanRecord:
    span_id: str
    name: str
    parent_span_id: str | None
    start_ts: float
    end_ts: float | None = None
    status: str = "ok"  # ok|error
    attrs: JsonDict = field(default_factory=dict)
    events: list[EventRecord] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "parent_span_id": self.parent_span_id,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "status": self.status,
            "attrs": self.attrs,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class TraceEnvelope:
    trace_id: str
    start_ts: float
    end_ts: float
    spans: list[SpanRecord] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)  # trace-level events

    def to_dict(self) -> JsonDict:
        return {
            "trace_id": self.trace_id,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "spans": [s.to_dict() for s in self.spans],
            "events": [e.to_dict() for e in self.events],
        }

