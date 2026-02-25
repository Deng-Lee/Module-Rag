from __future__ import annotations

from typing import Protocol

from ..vector_store.retriever import RankedCandidate


class Reranker(Protocol):
    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        ...
