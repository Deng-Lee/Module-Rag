from __future__ import annotations

from src.ingestion.stages import ChunkerStage, SectionerStage
from src.libs.providers.splitter import MarkdownHeadingsSectioner, RecursiveCharChunkerWithinSection


def test_sectioner_and_chunker_stable_ids() -> None:
    md_norm = (
        "# A\n"
        "\n"
        "Para1.\n\n"
        "![img](asset://aaaaaaaaaaaaaaaa)\n\n"
        "## B\n\n"
        "Para2.\n"
    )

    sectioner_stage = SectionerStage(sectioner=MarkdownHeadingsSectioner(max_section_level=2, include_heading=True))
    sections, sstats = sectioner_stage.run(md_norm, doc_id="doc_1")

    assert sstats["section_count"] >= 1
    assert isinstance(sstats["section_hash"], str)
    assert all(s.section_id.startswith("sec_") for s in sections)

    chunker_stage = ChunkerStage(chunker=RecursiveCharChunkerWithinSection(chunk_size=50, chunk_overlap=10))
    chunks, cstats = chunker_stage.run(sections)

    assert cstats["chunk_count"] >= 1
    assert isinstance(cstats["chunk_hash"], str)
    assert all(c.chunk_id.startswith("chk_") for c in chunks)

    # asset_ids should be preserved for markdown after rewrite
    assert any("asset_ids" in c.metadata for c in chunks)

    # stable ids across repeat
    sections2, _ = sectioner_stage.run(md_norm, doc_id="doc_1")
    chunks2, _ = chunker_stage.run(sections2)
    assert [c.chunk_id for c in chunks] == [c.chunk_id for c in chunks2]
