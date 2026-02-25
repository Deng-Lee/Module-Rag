from __future__ import annotations

from typing import Protocol


class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class SparseEncoder(Protocol):
    def encode(self, texts: list[str]) -> list[dict]:
        ...
