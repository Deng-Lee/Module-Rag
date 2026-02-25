from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass
class FakeEmbedder:
    """Deterministic embedder for tests and local runs."""

    dim: int = 8

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        if self.dim <= 0:
            raise ValueError("dim must be positive")

        seed = text.encode("utf-8")
        buf = hashlib.sha256(seed).digest()
        needed = self.dim * 4
        while len(buf) < needed:
            buf += hashlib.sha256(buf).digest()

        vec: list[float] = []
        for i in range(self.dim):
            chunk = buf[i * 4 : (i + 1) * 4]
            val = int.from_bytes(chunk, "big", signed=False)
            vec.append((val % 1_000_000) / 1_000_000.0)
        return vec
