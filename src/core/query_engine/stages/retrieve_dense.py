from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.vector_store import Candidate
from ..models import QueryIR, QueryParams, QueryRuntime


@dataclass
class DenseRetrieveStage:
    """Dense-only retrieval via the configured Retriever provider."""

    def run(self, q: QueryIR, runtime: QueryRuntime, params: QueryParams) -> list[Candidate]:
        _ = params  # D-2: keep params for later (filters, per-call profile overrides, etc.)
        return runtime.retriever.retrieve(q.query_norm, params.top_k)
