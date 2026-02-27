from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class McpSession:
    session_id: str
    client_level: str = "L0"  # L0|L1|L2
    trace_id: str | None = None

    @classmethod
    def new(cls, client_level: str = "L0", trace_id: str | None = None) -> "McpSession":
        return cls(session_id=f"sess_{uuid.uuid4().hex}", client_level=client_level, trace_id=trace_id)

