from __future__ import annotations

from src.libs.providers.loader import MarkdownLoader


def test_markdown_loader_assets(tmp_path) -> None:
    md = """# Title\n\nText.\n\n![alt](img/a.png)\n![b](https://example.com/b.png)\n"""
    p = tmp_path / "a.md"
    p.write_text(md, encoding="utf-8")

    loader = MarkdownLoader()
    out = loader.load(str(p))

    assert out.parse_summary.images == 2
    assert len(out.assets) == 2
    assert out.assets[0].source_type == "markdown"
    assert out.assets[0].origin_ref == "img/a.png"
    assert out.assets[0].anchor["line"] == 5
