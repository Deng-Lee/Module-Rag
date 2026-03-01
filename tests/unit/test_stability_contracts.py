from __future__ import annotations

from pathlib import Path

from src.ingestion.stages.storage.assets import AssetStore
from src.ingestion.stages.transform.base_transform import _compute_md_ref_id, normalize_markdown
from src.libs.providers.loader.markdown_loader import _compute_ref_id
from src.libs.interfaces.splitter import ChunkIR
from src.libs.providers.splitter import assign_chunk_ids
from src.libs.providers.splitter.recursive_chunker import canonical


def test_canonical_text_normalization_is_stable() -> None:
    raw = "\ufeffHello\r\nWorld \t\n"
    out = canonical(raw, profile_id="default")
    assert out == "Hello\nWorld"


def test_chunk_id_is_stable_for_same_section_and_text() -> None:
    chunks = [
        ChunkIR(chunk_id="", section_path="A", text="hello world", metadata={"section_id": "sec_1"})
    ]
    out1 = assign_chunk_ids(chunks, text_norm_profile_id="default")[0].chunk_id
    # Rebuild to avoid mutation side effects.
    chunks2 = [
        ChunkIR(chunk_id="", section_path="A", text="hello world", metadata={"section_id": "sec_1"})
    ]
    out2 = assign_chunk_ids(chunks2, text_norm_profile_id="default")[0].chunk_id
    assert out1 == out2


def test_chunk_id_changes_when_section_id_changes() -> None:
    c1 = ChunkIR(chunk_id="", section_path="A", text="hello world", metadata={"section_id": "sec_1"})
    c2 = ChunkIR(chunk_id="", section_path="A", text="hello world", metadata={"section_id": "sec_2"})
    id1 = assign_chunk_ids([c1], text_norm_profile_id="default")[0].chunk_id
    id2 = assign_chunk_ids([c2], text_norm_profile_id="default")[0].chunk_id
    assert id1 != id2


def test_asset_id_is_stable_for_same_bytes(tmp_path: Path) -> None:
    store = AssetStore(assets_dir=tmp_path / "assets")
    data = b"hello-asset"
    asset_id_1, _, reused1 = store.write_bytes(data, ".bin")
    asset_id_2, _, reused2 = store.write_bytes(data, ".bin")

    assert asset_id_1 == asset_id_2
    assert reused1 is False
    assert reused2 is True


def test_ref_id_is_consistent_between_loader_and_transform() -> None:
    url = "http://example.com/a.png"
    line = 10
    col = 5
    ref1 = _compute_ref_id(url, line, col)
    ref2 = _compute_md_ref_id(url, line, col)
    assert ref1 == ref2


def test_md_norm_is_stable() -> None:
    md = "a \r\n\r\n\r\nb\t\n"
    assert normalize_markdown(md, profile_id="default") == "a\n\nb\n"
