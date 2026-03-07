from __future__ import annotations

import os

import pytest

from src.libs.interfaces.vector_store import RankedCandidate
from src.libs.providers.reranker.cross_encoder import CrossEncoderReranker


@pytest.mark.integration
def test_cross_encoder_real_inference_smoke() -> None:
    """Run a real Cross-Encoder inference (no monkeypatch/no mock)."""
    model_name = os.environ.get("MODULE_RAG_CE_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    device = os.environ.get("MODULE_RAG_CE_DEVICE", "cpu")

    reranker = CrossEncoderReranker(
        model_name=model_name,
        device=device,
        max_candidates=2,
        batch_size=2,
        max_length=256,
        score_activation="raw",
    )

    candidates = [
        RankedCandidate(
            chunk_id="relevant",
            score=0.5,
            rank=1,
            source="rrf",
            metadata={"rerank_text": "Paris is the capital of France."},
        ),
        RankedCandidate(
            chunk_id="irrelevant",
            score=0.5,
            rank=2,
            source="rrf",
            metadata={"rerank_text": "Bananas are yellow fruits rich in potassium."},
        ),
    ]

    out = reranker.rerank("What is the capital of France?", candidates)
    assert len(out) == 2
    assert {x.chunk_id for x in out} == {"relevant", "irrelevant"}
    assert out[0].chunk_id == "relevant"
