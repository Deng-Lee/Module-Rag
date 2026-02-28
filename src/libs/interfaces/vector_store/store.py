from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class VectorItem:
    chunk_id: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorIndex(Protocol):
    def upsert(self, items: list[VectorItem]) -> None:
        ...

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        ...

    def delete(self, chunk_ids: list[str]) -> None:
        ...


class SparseIndex(Protocol):
    def upsert(self, items: list[dict[str, Any]]) -> None:
        ...

    def query(self, query_expr: str, top_k: int) -> list[tuple[str, float]]:
        ...
