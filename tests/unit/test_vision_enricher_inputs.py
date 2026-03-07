from __future__ import annotations

from src.libs.providers.enricher.openai_compatible_vision import collect_asset_ids


def test_collect_asset_ids_from_markdown_text() -> None:
    asset_id = "a" * 64
    text = f"See image ![x](asset://{asset_id}) in the doc."
    out = collect_asset_ids(text, metadata={})
    assert out == [asset_id]


def test_collect_asset_ids_from_pdf_metadata() -> None:
    asset_id = "b" * 64
    out = collect_asset_ids("facts without links", metadata={"asset_ids": [asset_id]})
    assert out == [asset_id]


def test_collect_asset_ids_dedup_and_order() -> None:
    a1 = "c" * 64
    a2 = "d" * 64
    text = f"![a](asset://{a1}) and again asset://{a1}"
    metadata = {"asset_ids": [a2, a1]}
    out = collect_asset_ids(text, metadata=metadata)
    assert out == [a1, a2]
