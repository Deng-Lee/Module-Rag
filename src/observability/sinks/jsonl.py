from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ..trace.envelope import TraceEnvelope


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    return obj


class JsonlSink:
    """
    Append-only JSONL sink for trace envelopes.

    If path_or_dir is a directory, a default file name is used.
    """

    def __init__(self, path_or_dir: str | Path, rotate_policy: Any | None = None) -> None:
        p = Path(path_or_dir)
        if p.suffix == ".jsonl":
            self.path = p
        elif p.is_dir() or str(path_or_dir).endswith(("/", "\\")):
            self.path = p / "traces.jsonl"
        else:
            # Treat non-existing path without suffix as directory.
            self.path = p / "traces.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rotate_policy = rotate_policy

    def write(self, envelope: TraceEnvelope) -> None:
        record = envelope.to_dict()
        line = json.dumps(record, ensure_ascii=True, default=_to_jsonable)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # --- ObsSink compatibility (optional) ---
    def on_event(self, record: dict[str, Any]) -> None:  # noqa: D401
        """No-op for now; JSONL sink focuses on trace envelopes."""
        return

    def on_metric(self, record: dict[str, Any]) -> None:  # noqa: D401
        """No-op for now; JSONL sink focuses on trace envelopes."""
        return

    def on_span_end(self, record: dict[str, Any]) -> None:  # noqa: D401
        """No-op for now; JSONL sink focuses on trace envelopes."""
        return

    def on_trace_end(self, envelope: TraceEnvelope) -> None:
        self.write(envelope)
