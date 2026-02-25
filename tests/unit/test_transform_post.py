from __future__ import annotations

import pytest

from src.ingestion.stages import NoopEnricher, RetrievalViewConfig, TransformPostStage, build_chunk_retrieval_text
from src.libs.interfaces.splitter import ChunkIR


def test_build_chunk_retrieval_text_facts_only() -> None:
    out = build_chunk_retrieval_text("facts", template_id="facts_only", enrichments={"caption": "x"})
    assert out == "facts"


def test_build_chunk_retrieval_text_facts_plus_enrich() -> None:
    out = build_chunk_retrieval_text(
        "facts",
        template_id="facts_plus_enrich",
        enrichments={"caption": "cap", "keywords": ["k1", "k2"]},
    )
    assert "facts" in out
    assert "[caption] cap" in out
    assert "[keywords] k1" in out


def test_transform_post_noop_does_not_change_chunk_text() -> None:
    chunks = [ChunkIR(chunk_id="c1", section_path="A", text="facts", metadata={"section_path": "A"})]
    stage = TransformPostStage(view_cfg=RetrievalViewConfig(template_id="facts_plus_enrich"), enrichers=[NoopEnricher()])
    out = stage.run(chunks)

    assert out[0].text == "facts"
    assert out[0].metadata["chunk_retrieval_text"].startswith("facts")


def test_transform_post_unknown_template_errors() -> None:
    chunks = [ChunkIR(chunk_id="c1", section_path="A", text="facts", metadata={})]
    stage = TransformPostStage(view_cfg=RetrievalViewConfig(template_id="unknown"))
    with pytest.raises(ValueError):
        stage.run(chunks)
