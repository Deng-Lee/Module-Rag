"""User-facing observability API (span/event/metric)."""

from .api import emit_stage_summary, event, metric, set_sink, span, with_stage

__all__ = ["span", "event", "metric", "set_sink", "with_stage", "emit_stage_summary"]
