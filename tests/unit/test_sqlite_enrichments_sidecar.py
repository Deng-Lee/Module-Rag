from __future__ import annotations

from pathlib import Path

from src.ingestion.stages.storage.sqlite import SqliteStore


def test_asset_enrichment_upsert_idempotent(tmp_path: Path) -> None:
    store = SqliteStore(db_path=tmp_path / "app.sqlite")
    store.upsert_asset_enrichment(
        asset_id="a" * 64,
        provider_id="vision.openai_compatible",
        model="gpt-4o-mini",
        profile_id="p1",
        ocr_text="ocr v1",
        caption_text="cap v1",
        raw_json='{"v":1}',
    )
    store.upsert_asset_enrichment(
        asset_id="a" * 64,
        provider_id="vision.openai_compatible",
        model="gpt-4o-mini",
        profile_id="p1",
        ocr_text="ocr v2",
        caption_text="cap v2",
        raw_json='{"v":2}',
    )

    with store._connect() as conn:  # type: ignore[attr-defined]
        row = conn.execute(
            """
            SELECT COUNT(*) AS c, ocr_text, caption_text
            FROM asset_enrichments
            WHERE asset_id=? AND provider_id=? AND model=? AND profile_id=?
            """,
            ("a" * 64, "vision.openai_compatible", "gpt-4o-mini", "p1"),
        ).fetchone()

    assert int(row["c"]) == 1
    assert row["ocr_text"] == "ocr v2"
    assert row["caption_text"] == "cap v2"


def test_chunk_enrichment_upsert_and_fetch(tmp_path: Path) -> None:
    store = SqliteStore(db_path=tmp_path / "app.sqlite")
    store.upsert_chunk_enrichment(
        chunk_id="c1",
        provider_id="vision.openai_compatible",
        model="gpt-4o-mini",
        profile_id="p1",
        retrieval_template_id="facts_plus_enrich",
        vision_snippets_json='["[image_caption asset_id=a] cap"]',
    )

    out = store.fetch_chunk_enrichments(["c1"])
    assert "c1" in out
    assert out["c1"]["items"]
    item = out["c1"]["items"][0]
    assert item["provider_id"] == "vision.openai_compatible"
    assert item["model"] == "gpt-4o-mini"
    assert item["profile_id"] == "p1"
    assert item["retrieval_template_id"] == "facts_plus_enrich"
