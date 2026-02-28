from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


JsonDict = dict[str, Any]

TRACE_SCHEMA_VERSION = "trace.v1"
STAGE_PREFIX = "stage."

# Stable, finite event kinds for dashboard + replay.
# NOTE: keep this list synchronized with DEV_SPEC (3.5.2 / F-1).
ALLOWED_EVENT_KINDS: set[str] = {
    "stage.start",
    "stage.end",
    "stage.error",
    "retrieval.candidates",
    "retrieval.fused",
    "fusion.ranked",
    "rerank.ranked",
    "rerank.used",
    "rerank.skipped",
    "warn.rerank_fallback",
    "context.built",
    "generate.used",
    "generate.skipped",
    "warn.generate_fallback",
    "ingest.upsert_result",
    "metric",
    "error",
    "warn.span_leak",
    "event.unknown",
}


def _normalize_event_kind(kind: str, *, strict: bool) -> str:
    k = (kind or "").strip()
    if k in ALLOWED_EVENT_KINDS:
        return k
    if strict:
        raise ValueError(f"invalid event.kind: {kind!r}")
    return k


def _validate_stage_name(name: str, *, strict: bool) -> None:
    if not strict:
        return
    if not name.startswith(STAGE_PREFIX):
        raise ValueError(f"invalid span.name (must start with {STAGE_PREFIX!r}): {name!r}")


def new_event(
    kind: str,
    attrs: JsonDict | None = None,
    *,
    ts: float | None = None,
    strict: bool = False,
) -> "EventRecord":
    k = _normalize_event_kind(kind, strict=strict)
    return EventRecord(ts=0.0 if ts is None else ts, kind=k, attrs=dict(attrs or {}))


def new_span(
    *,
    span_id: str,
    name: str,
    parent_span_id: str | None,
    start_ts: float,
    attrs: JsonDict | None = None,
    strict: bool = False,
) -> "SpanRecord":
    _validate_stage_name(name, strict=strict)
    return SpanRecord(
        span_id=span_id,
        name=name,
        parent_span_id=parent_span_id,
        start_ts=start_ts,
        attrs=dict(attrs or {}),
    )


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
    trace_type: str = "unknown"  # ingestion|query|unknown
    status: str = "ok"  # ok|error
    strategy_config_id: str = "unknown"
    spans: list[SpanRecord] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)  # trace-level events
    aggregates: JsonDict = field(default_factory=dict)
    providers: JsonDict = field(default_factory=dict)
    schema_version: str = TRACE_SCHEMA_VERSION

    def to_dict(self) -> JsonDict:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "status": self.status,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "strategy_config_id": self.strategy_config_id,
            "spans": [s.to_dict() for s in self.spans],
            "events": [e.to_dict() for e in self.events],
            "aggregates": self.aggregates,
            "providers": self.providers,
        }

    def validate(self, *, strict: bool = True) -> None:
        if not self.trace_id:
            raise ValueError("trace_id missing")
        if strict:
            for span in self.spans:
                _validate_stage_name(span.name, strict=True)
                for ev in span.events:
                    _normalize_event_kind(ev.kind, strict=True)
            for ev in self.events:
                _normalize_event_kind(ev.kind, strict=True)

    def iter_event_kinds(self) -> Iterable[str]:
        for s in self.spans:
            for ev in s.events:
                yield ev.kind
        for ev in self.events:
            yield ev.kind
