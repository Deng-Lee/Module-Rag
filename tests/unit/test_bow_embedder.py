from __future__ import annotations

from src.libs.providers.embedding.bow_embedder import BowHashEmbedder


def test_bow_embedder_deterministic_and_overlap() -> None:
    e = BowHashEmbedder(dim=64)
    v1 = e.embed_texts(["sqlite fts5 bm25"])[0]
    v2 = e.embed_texts(["sqlite fts5 bm25"])[0]
    assert v1 == v2

    # Overlap should be higher than unrelated text (rough check).
    a = e.embed_texts(["sqlite fts5 bm25"])[0]
    b = e.embed_texts(["fts5 sqlite query"])[0]
    c = e.embed_texts(["image caption ocr"])[0]

    def dot(x, y):
        return sum(i * j for i, j in zip(x, y))

    assert dot(a, b) > dot(a, c)

