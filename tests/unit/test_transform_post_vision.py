from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.ingestion.stages import RetrievalViewConfig, TransformPostStage
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.libs.interfaces.splitter import ChunkIR


@dataclass
class FakeVisionEnricher:
    provider_id: str = "vision.fake"
    model: str = "fake-model"
    profile_id: str = "p1"

    def enrich(self, chunk):  # type: ignore[override]
        _ = chunk
        return {
            "vision_snippets": ["[image_caption asset_id=a] a caption"],
            "vision_assets": [
                {"asset_id": "a" * 64, "caption": "a caption", "ocr_text": "ocr text", "raw": {"v": 1}}
            ],
        }


def test_transform_post_writes_sidecar_and_keeps_facts(tmp_path: Path) -> None:
    sqlite = SqliteStore(db_path=tmp_path / "app.sqlite")
    chunks = [ChunkIR(chunk_id="c1", section_path="S", text="facts", metadata={"section_path": "S"})]
    stage = TransformPostStage(
        view_cfg=RetrievalViewConfig(template_id="facts_plus_enrich"),
        enrichers=[FakeVisionEnricher()],
        sqlite=sqlite,
    )

    out = stage.run(chunks)

    assert out[0].text == "facts"
    assert "a caption" in out[0].metadata["chunk_retrieval_text"]

    # Verify chunk enrichment stored.
    rows = sqlite.fetch_chunk_enrichments(["c1"])
    assert "c1" in rows
    item = rows["c1"]["items"][0]
    assert item["provider_id"] == "vision.fake"
    assert item["model"] == "fake-model"
    assert item["profile_id"] == "p1"
    assert item["retrieval_template_id"] == "facts_plus_enrich"
    assert json.loads(item["vision_snippets_json"])

