from __future__ import annotations

import pytest

from pathlib import Path

from src.ingestion.stages import LoaderStage, detect_file_type
from src.libs.providers.loader import MarkdownLoader


def test_detect_file_type() -> None:
    assert detect_file_type(Path("a.md")) == "md"
    assert detect_file_type(Path("a.markdown")) == "md"
    assert detect_file_type(Path("a.pdf")) == "pdf"
    with pytest.raises(ValueError):
        detect_file_type(Path("a.txt"))


def test_loader_stage_markdown(tmp_path) -> None:
    p = tmp_path / "a.md"
    p.write_text("hello", encoding="utf-8")

    stage = LoaderStage(loaders={"md": MarkdownLoader()})
    out = stage.run(str(p), doc_id="doc_1", version_id="ver_1")

    assert out.md == "hello"
    assert out.doc_id == "doc_1"
    assert out.version_id == "ver_1"
