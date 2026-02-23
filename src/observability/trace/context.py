from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import contextvars
import time
import traceback
import uuid
from typing import Any, Iterator

from .envelope import EventRecord, SpanRecord, TraceEnvelope


_CTX: contextvars.ContextVar["TraceContext | None"] = contextvars.ContextVar(
    "trace_context", default=None
)


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass
class TraceContext:
    trace_id: str
    start_ts: float
    _spans_by_id: dict[str, SpanRecord] = field(default_factory=dict)
    _span_stack: list[str] = field(default_factory=list)
    _span_order: list[str] = field(default_factory=list)
    _trace_events: list[EventRecord] = field(default_factory=list)

    @classmethod
    def new(cls, trace_id: str | None = None) -> "TraceContext":
        return cls(trace_id=trace_id or _new_id("trace"), start_ts=_now())

    @classmethod
    def current(cls) -> "TraceContext | None":
        return _CTX.get()

    @classmethod
    @contextmanager
    def activate(cls, ctx: "TraceContext") -> Iterator["TraceContext"]:
        token = _CTX.set(ctx)
        try:
            yield ctx
        finally:
            _CTX.reset(token)

    def _current_span(self) -> SpanRecord | None:
        if not self._span_stack:
            return None
        return self._spans_by_id.get(self._span_stack[-1])

    def current_span(self) -> SpanRecord | None:
        return self._current_span()

    @contextmanager
    def start_span(self, name: str, attrs: dict[str, Any] | None = None) -> Iterator[SpanRecord]:
        span_id = _new_id("span")
        parent = self._span_stack[-1] if self._span_stack else None
        s = SpanRecord(
            span_id=span_id,
            name=name,
            parent_span_id=parent,
            start_ts=_now(),
            attrs=dict(attrs or {}),
        )
        self._spans_by_id[span_id] = s
        self._span_stack.append(span_id)
        self._span_order.append(span_id)

        try:
            yield s
        except Exception as e:
            # Record error as span-local event; keep it concise + debuggable.
            s.status = "error"
            self.add_event(
                "error",
                {
                    "exc_type": type(e).__name__,
                    "message": str(e),
                    "traceback": "".join(traceback.format_exc(limit=5)),
                },
            )
            raise
        finally:
            # Ensure proper close and stack pop even on exception.
            if self._span_stack and self._span_stack[-1] == span_id:
                self._span_stack.pop()
            s.end_ts = _now()

    def add_event(self, kind: str, attrs: dict[str, Any] | None = None) -> EventRecord:
        ev = EventRecord(ts=_now(), kind=kind, attrs=dict(attrs or {}))
        cur = self._current_span()
        if cur is None:
            self._trace_events.append(ev)
        else:
            cur.events.append(ev)
        return ev

    def finish(self) -> TraceEnvelope:
        # Auto-close any leaked spans to keep traces well-formed.
        if self._span_stack:
            self._trace_events.append(
                EventRecord(
                    ts=_now(),
                    kind="warn.span_leak",
                    attrs={"open_span_count": len(self._span_stack)},
                )
            )
            while self._span_stack:
                sid = self._span_stack.pop()
                s = self._spans_by_id.get(sid)
                if s and s.end_ts is None:
                    s.status = "error"
                    s.end_ts = _now()

        end_ts = _now()
        spans = [self._spans_by_id[sid] for sid in self._span_order if sid in self._spans_by_id]
        return TraceEnvelope(
            trace_id=self.trace_id,
            start_ts=self.start_ts,
            end_ts=end_ts,
            spans=spans,
            events=list(self._trace_events),
        )
