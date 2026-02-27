from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.vector_store import Candidate
from ..models import QueryIR, QueryParams, QueryRuntime


@dataclass
class SparseRetrieveStage:
    """Sparse-only retrieval via the configured sparse retriever provider."""

    def run(self, q: QueryIR, runtime: QueryRuntime, params: QueryParams) -> list[Candidate]:
        if runtime.sparse_retriever is None:
            return []
        _ = params
        return runtime.sparse_retriever.retrieve(q.query_norm, params.top_k)

