from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Protocol

from ..trace.context import TraceContext
from ..trace.envelope import EventRecord, SpanRecord, TraceEnvelope


class ObsSink(Protocol):
    def on_event(self, record: dict[str, Any]) -> None: ...

    def on_metric(self, record: dict[str, Any]) -> None: ...

    def on_span_end(self, record: dict[str, Any]) -> None: ...

    def on_trace_end(self, envelope: TraceEnvelope) -> None: ...


_SINK: ObsSink | None = None


def set_sink(sink: ObsSink | None) -> None:
    global _SINK
    _SINK = sink


def get_sink() -> ObsSink | None:
    return _SINK


def _current() -> TraceContext | None:
    return TraceContext.current()


def _span_record(trace_id: str, span: SpanRecord) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "span_id": span.span_id,
        "parent_span_id": span.parent_span_id,
        "name": span.name,
        "status": span.status,
        "start_ts": span.start_ts,
        "end_ts": span.end_ts,
        "attrs": span.attrs,
    }


def _event_record(trace_id: str, span_id: str | None, ev: EventRecord) -> dict[str, Any]:
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "ts": ev.ts,
        "kind": ev.kind,
        "attrs": ev.attrs,
    }


@contextmanager
def span(name: str, attrs: dict[str, Any] | None = None) -> Iterator[SpanRecord | None]:
    """
    Create a span if a TraceContext is active; otherwise degrade to no-op.
    """
    ctx = _current()
    if ctx is None:
        yield None
        return

    with ctx.start_span(name, attrs) as s:
        try:
            yield s
        finally:
            if _SINK is not None:
                _SINK.on_span_end(_span_record(ctx.trace_id, s))


def event(kind: str, attrs: dict[str, Any] | None = None) -> None:
    """
    Emit a structured event bound to the current span if present.
    """
    ctx = _current()
    if ctx is None:
        return

    ev = ctx.add_event(kind, attrs)
    if _SINK is not None:
        span = ctx.current_span()
        _SINK.on_event(_event_record(ctx.trace_id, span.span_id if span else None, ev))


def metric(name: str, value: float | int, attrs: dict[str, Any] | None = None) -> None:
    """
    Emit a metric as a structured record (and also as an event for now).
    """
    ctx = _current()
    if ctx is None:
        return

    payload = {"name": name, "value": value}
    if attrs:
        payload.update(attrs)

    ev = ctx.add_event("metric", payload)
    if _SINK is not None:
        span = ctx.current_span()
        _SINK.on_metric(
            {
                "trace_id": ctx.trace_id,
                "span_id": span.span_id if span else None,
                "ts": ev.ts,
                "name": name,
                "value": value,
                "attrs": attrs or {},
            }
        )


def _normalize_stage_name(stage_name: str) -> str:
    name = (stage_name or "").strip()
    if name.startswith("stage."):
        return name[len("stage.") :]
    return name


@contextmanager
def with_stage(
    stage_name: str,
    attrs: dict[str, Any] | None = None,
    summary: dict[str, Any] | None = None,
) -> Iterator[SpanRecord | None]:
    """
    Wrap a pipeline stage with a stable span + stage.start/end/error events.
    """
    stage_key = _normalize_stage_name(stage_name)
    span_attrs = {"stage": stage_key}
    if attrs:
        span_attrs.update(attrs)

    with span(f"stage.{stage_key}", span_attrs) as s:
        event("stage.start", {"stage": stage_key, **(attrs or {})})
        try:
            yield s
        except Exception as e:
            event(
                "stage.error",
                {"stage": stage_key, "message": str(e), "exc_type": type(e).__name__},
            )
            raise
        finally:
            end_attrs = {"stage": stage_key}
            if summary:
                end_attrs.update(summary)
            event("stage.end", end_attrs)


def emit_stage_summary(stage_name: str, summary: dict[str, Any]) -> None:
    stage_key = _normalize_stage_name(stage_name)
    event("stage.end", {"stage": stage_key, **(summary or {})})
