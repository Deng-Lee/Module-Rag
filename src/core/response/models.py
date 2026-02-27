from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...observability.trace.envelope import TraceEnvelope


@dataclass(frozen=True)
class SourceRef:
    """A minimal, UI-friendly reference to a retrieved chunk."""

    chunk_id: str
    score: float
    source: str  # dense|sparse|hybrid|...
    rank: int | None = None
    citation_id: str | None = None
    asset_ids: list[str] | None = None

    doc_id: str | None = None
    version_id: str | None = None
    section_path: str | None = None
    chunk_index: int | None = None


@dataclass
class ResponseIR:
    """Transport-agnostic response envelope (MCP will adapt later)."""

    trace_id: str
    content_md: str
    sources: list[SourceRef] = field(default_factory=list)
    structured: dict[str, Any] = field(default_factory=dict)

    # For tests/debug; MCP tool can choose to omit this from client response.
    trace: TraceEnvelope | None = None
