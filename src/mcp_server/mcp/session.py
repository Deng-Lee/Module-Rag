from __future__ import annotations

import time
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class McpSession:
    session_id: str
    client_level: str = "L0"  # L0|L1|L2
    trace_id: str | None = None
    deadline_ts: float | None = None  # unix timestamp; best-effort (no task killing in MVP)

    @classmethod
    def new(cls, client_level: str = "L0", trace_id: str | None = None) -> "McpSession":
        return cls(session_id=f"sess_{uuid.uuid4().hex}", client_level=client_level, trace_id=trace_id)

    def new_call(self, *, trace_id: str | None = None) -> "McpSession":
        """Create a per-tool-call session view with a fresh trace_id.

        E-8 note: this is a protocol-layer trace_id used for request scoping and
        error attribution. Core ingestion/query may still generate their own
        internal trace ids until we fully unify them in later milestones.
        """
        tid = trace_id or f"trace_{uuid.uuid4().hex}"
        return McpSession(
            session_id=self.session_id,
            client_level=self.client_level,
            trace_id=tid,
            deadline_ts=self.deadline_ts,
        )

    def with_deadline(self, timeout_ms: int) -> "McpSession":
        """Return a session view with a (best-effort) deadline."""
        if timeout_ms <= 0:
            deadline = time.time()
        else:
            deadline = time.time() + (timeout_ms / 1000.0)
        return McpSession(
            session_id=self.session_id,
            client_level=self.client_level,
            trace_id=self.trace_id,
            deadline_ts=deadline,
        )
