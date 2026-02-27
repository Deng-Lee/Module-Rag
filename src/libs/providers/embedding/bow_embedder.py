from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass


_TOK_RE = re.compile(r"[0-9A-Za-z_]+|[\u4e00-\u9fff]+")


@dataclass
class BowHashEmbedder:
    """Deterministic bag-of-words embedder via feature hashing (test/dev friendly).

    This is not a semantic model; it approximates lexical overlap so that
    integration tests can use natural queries without requiring external APIs.
    """

    dim: int = 64

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.dim <= 0:
            raise ValueError("dim must be positive")
        return [self._embed_one(t or "") for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = _TOK_RE.findall(text.lower())
        for tok in tokens:
            h = hashlib.sha256(tok.encode("utf-8")).digest()
            idx = int.from_bytes(h[:4], "big") % self.dim
            vec[idx] += 1.0

        n = math.sqrt(sum(v * v for v in vec))
        if n > 0.0:
            vec = [v / n for v in vec]
        return vec

