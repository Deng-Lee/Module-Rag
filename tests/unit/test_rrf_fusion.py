from __future__ import annotations

from src.libs.interfaces.vector_store import Candidate
from src.libs.providers.vector_store.rrf_fusion import RrfFusion


def test_rrf_fusion_prefers_items_appearing_in_multiple_lists() -> None:
    fusion = RrfFusion(k=60)

    dense = [
        Candidate(chunk_id="A", score=0.9, source="dense"),
        Candidate(chunk_id="B", score=0.8, source="dense"),
        Candidate(chunk_id="C", score=0.7, source="dense"),
    ]
    sparse = [
        Candidate(chunk_id="C", score=10.0, source="sparse"),
        Candidate(chunk_id="A", score=9.0, source="sparse"),
        Candidate(chunk_id="D", score=8.0, source="sparse"),
    ]

    ranked = fusion.fuse({"dense": dense, "sparse": sparse})
    ids = [r.chunk_id for r in ranked]

    # A and C appear twice; they should rank ahead of single-source D in most cases.
    assert ids.index("A") < ids.index("D")
    assert ids.index("C") < ids.index("D")


def test_rrf_fusion_empty_inputs() -> None:
    assert RrfFusion().fuse({}) == []

