from __future__ import annotations

from dataclasses import dataclass

from ...interfaces.vector_store.retriever import RankedCandidate


@dataclass
class NoopReranker:
    """No-op reranker that preserves input order."""

    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        return candidates
