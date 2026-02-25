from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Candidate:
    chunk_id: str
    score: float
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RankedCandidate:
    chunk_id: str
    score: float
    rank: int
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Retriever(Protocol):
    def retrieve(self, query: str, top_k: int) -> list[Candidate]:
        ...


class Fusion(Protocol):
    def fuse(self, candidates_by_source: dict[str, list[Candidate]]) -> list[RankedCandidate]:
        ...
