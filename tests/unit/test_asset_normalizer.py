from __future__ import annotations

from pathlib import Path

from src.ingestion.stages import AssetStore, FsAssetNormalizer
from src.libs.interfaces.loader import AssetRef


def test_asset_normalizer_markdown_dedup(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    md_path = tmp_path / "doc.md"
    md_path.write_text("![a](img.png)", encoding="utf-8")

    img_path = tmp_path / "img.png"
    img_path.write_bytes(b"IMGDATA")

    assets = [
        AssetRef(ref_id="r1", source_type="markdown", origin_ref="img.png", anchor={"line": 1}),
        AssetRef(ref_id="r2", source_type="markdown", origin_ref="img.png", anchor={"line": 1}),
    ]

    normalizer = FsAssetNormalizer(asset_store=AssetStore(assets_dir=assets_dir))
    out = normalizer.normalize(assets, raw_path=str(md_path), md=md_path.read_text())

    assert out.assets_new == 1
    assert out.assets_reused == 1
    assert out.assets_failed == 0
    assert out.ref_to_asset_id["r1"] == out.ref_to_asset_id["r2"]

    asset_id = out.ref_to_asset_id["r1"]
    stored = assets_dir / f"{asset_id}.png"
    assert stored.exists()


def _build_pdf_with_image() -> bytes:
    header = b"%PDF-1.4\n"
    objs: list[bytes] = []

    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /Resources << /XObject << /Im1 10 0 R >> >> >>\n"
        b"endobj\n"
    )
    objs.append(b"4 0 obj\n<< /Length 0 >>\nstream\n\nendstream\nendobj\n")
    objs.append(
        b"10 0 obj\n"
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB "
        b"/BitsPerComponent 8 /Length 3 >>\n"
        b"stream\n\x00\x00\x00\nendstream\nendobj\n"
    )

    offsets = [0]
    current = len(header)
    for obj in objs:
        offsets.append(current)
        current += len(obj)

    xref = [b"xref\n", f"0 {len(objs)+1}\n".encode("latin1")]
    xref.append(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n \n".encode("latin1"))

    xref_bytes = b"".join(xref)
    trailer = (
        b"trailer\n"
        + f"<< /Size {len(objs)+1} /Root 1 0 R >>\n".encode("latin1")
        + b"startxref\n"
        + f"{current}\n".encode("latin1")
        + b"%%EOF\n"
    )

    return header + b"".join(objs) + xref_bytes + trailer


def test_asset_normalizer_pdf_obj(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    pdf_path = tmp_path / "a.pdf"
    pdf_path.write_bytes(_build_pdf_with_image())

    assets = [
        AssetRef(ref_id="r1", source_type="pdf", origin_ref="pdf_obj:10", anchor={"obj": 10}),
    ]

    normalizer = FsAssetNormalizer(asset_store=AssetStore(assets_dir=assets_dir))
    out = normalizer.normalize(assets, raw_path=str(pdf_path), md="")

    assert out.assets_new == 1
    assert out.assets_failed == 0
    asset_id = out.ref_to_asset_id["r1"]
    stored = assets_dir / f"{asset_id}.bin"
    assert stored.exists()
