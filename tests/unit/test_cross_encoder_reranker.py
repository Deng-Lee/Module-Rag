from __future__ import annotations

from src.libs.interfaces.vector_store import RankedCandidate
from src.libs.providers.reranker.cross_encoder import CrossEncoderReranker


def _candidates() -> list[RankedCandidate]:
    return [
        RankedCandidate(chunk_id="a", score=0.9, rank=1, source="rrf", metadata={"rerank_text": "alpha"}),
        RankedCandidate(chunk_id="b", score=0.8, rank=2, source="rrf", metadata={"rerank_text": "beta"}),
        RankedCandidate(chunk_id="c", score=0.7, rank=3, source="rrf", metadata={"rerank_text": "gamma"}),
    ]


def test_cross_encoder_rerank_changes_order(monkeypatch) -> None:
    rr = CrossEncoderReranker(model_name="dummy", max_candidates=3, score_activation="raw")
    monkeypatch.setattr(CrossEncoderReranker, "_predict_pairs", lambda self, pairs: [0.1, 0.95, 0.2])

    out = rr.rerank("query", _candidates())
    assert [x.chunk_id for x in out] == ["b", "c", "a"]


def test_cross_encoder_rerank_tie_breaks_by_original_rank(monkeypatch) -> None:
    rr = CrossEncoderReranker(model_name="dummy", max_candidates=3, score_activation="raw")
    monkeypatch.setattr(CrossEncoderReranker, "_predict_pairs", lambda self, pairs: [0.5, 0.5, 0.5])

    out = rr.rerank("query", _candidates())
    assert [x.chunk_id for x in out] == ["a", "b", "c"]


def test_cross_encoder_rerank_respects_max_candidates(monkeypatch) -> None:
    rr = CrossEncoderReranker(model_name="dummy", max_candidates=2, score_activation="raw")
    monkeypatch.setattr(CrossEncoderReranker, "_predict_pairs", lambda self, pairs: [0.9, 0.1])

    out = rr.rerank("query", _candidates())
    # only top-2 are reranked; tail candidate "c" stays at end.
    assert [x.chunk_id for x in out] == ["a", "b", "c"]


def test_cross_encoder_rerank_no_text_keeps_input() -> None:
    rr = CrossEncoderReranker(model_name="dummy", max_candidates=3, score_activation="raw")
    inp = [
        RankedCandidate(chunk_id="a", score=0.9, rank=1, source="rrf", metadata={}),
        RankedCandidate(chunk_id="b", score=0.8, rank=2, source="rrf", metadata={}),
    ]
    out = rr.rerank("query", inp)
    assert out == inp
