from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol


class EmbeddingCache(Protocol):
    def get(self, key: str) -> list[float] | None:
        ...

    def put(self, key: str, vector: list[float]) -> None:
        ...


@dataclass
class InMemoryEmbeddingCache:
    _store: dict[str, list[float]] = field(default_factory=dict)

    def get(self, key: str) -> list[float] | None:
        return self._store.get(key)

    def put(self, key: str, vector: list[float]) -> None:
        self._store[key] = vector


def canonical(text: str, *, profile_id: str = "default") -> str:
    """Canonicalize text for stable hashing/embedding.

    This must match the embedding input used by the encoder so that
    cache_key == actual vector input.
    """

    _ = profile_id  # reserved for versioned profiles

    if text.startswith("\ufeff"):
        text = text[1:]

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    out_chars: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in {"Cc", "Cf"} and ch not in {"\n", "\t"}:
            continue
        out_chars.append(ch)
    text = "".join(out_chars)

    lines = [ln.rstrip(" \t") for ln in text.split("\n")]
    return "\n".join(lines).strip("\n")


def content_hash(text: str, *, text_norm_profile_id: str) -> str:
    c = canonical(text, profile_id=text_norm_profile_id)
    return hashlib.sha256(c.encode("utf-8")).hexdigest()


def make_embedding_cache_key(
    *,
    text_norm_profile_id: str,
    content_hash: str,
    embedder_id: str,
    embedder_version: str,
) -> str:
    return f"{embedder_id}:{embedder_version}:{text_norm_profile_id}:{content_hash}"
