"""User-facing observability API (span/event/metric)."""

from .api import event, metric, set_sink, span

__all__ = ["span", "event", "metric", "set_sink"]

