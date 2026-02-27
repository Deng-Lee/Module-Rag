from __future__ import annotations

import re

from ..models import QueryIR


def query_norm(query: str) -> QueryIR:
    """Normalize user query for stable retrieval behavior (no semantics change)."""
    raw = query if isinstance(query, str) else str(query)
    s = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    s = re.sub(r"\s+", " ", s)
    return QueryIR(query_raw=raw, query_norm=s)

