from __future__ import annotations

from pathlib import Path

from src.libs.providers.loader import PdfLoader


def _build_min_pdf(text: str) -> bytes:
    header = b"%PDF-1.4\n"
    objs: list[bytes] = []

    objs.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objs.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objs.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
    )
    stream = f"BT /F1 24 Tf 72 72 Td ({text}) Tj ET".encode("latin1")
    objs.append(
        b"4 0 obj\n"
        + f"<< /Length {len(stream)} >>\n".encode("latin1")
        + b"stream\n"
        + stream
        + b"\nendstream\nendobj\n"
    )
    objs.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")

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


def test_pdf_loader_minimal(tmp_path: Path) -> None:
    pdf_bytes = _build_min_pdf("Hello PDF")
    p = tmp_path / "a.pdf"
    p.write_bytes(pdf_bytes)

    loader = PdfLoader()
    out = loader.load(str(p))

    assert "Hello PDF" in out.md
    assert out.parse_summary.images == 0
    assert out.assets == []
    assert out.parse_summary.pages in {None, 1}
