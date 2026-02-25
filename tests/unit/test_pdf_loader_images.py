from __future__ import annotations

from pathlib import Path

from src.libs.providers.loader import PdfLoader


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


def test_pdf_loader_image_anchor_page(tmp_path: Path) -> None:
    pdf_bytes = _build_pdf_with_image()
    p = tmp_path / "img.pdf"
    p.write_bytes(pdf_bytes)

    loader = PdfLoader()
    out = loader.load(str(p))

    assert out.parse_summary.images == 1
    assert len(out.assets) == 1
    anchor = out.assets[0].anchor
    assert anchor.get("page") == 1
    assert anchor.get("obj") == 10
