from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ...interfaces.loader import AssetRef, LoaderOutput, ParseSummary


_IMG_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)")


@dataclass
class MarkdownLoader:
    """Minimal Markdown loader (assets manifest only)."""

    def load(self, input_path: str, *, doc_id: str | None = None, version_id: str | None = None) -> LoaderOutput:
        p = Path(input_path)
        md = p.read_text(encoding="utf-8")

        assets: list[AssetRef] = []
        for line_no, line in enumerate(md.splitlines(), start=1):
            for match in _IMG_RE.finditer(line):
                url = match.group("url")
                alt = match.group("alt")
                col = match.start() + 1
                ref_id = _compute_ref_id(url, line_no, col)
                assets.append(
                    AssetRef(
                        ref_id=ref_id,
                        source_type="markdown",
                        origin_ref=url,
                        anchor={"line": line_no, "col": col},
                        context_hint=alt or None,
                    )
                )

        summary = ParseSummary(
            pages=None,
            paragraphs=_count_paragraphs(md),
            images=len(assets),
            text_chars=len(md),
            warnings=[],
            errors=None,
        )

        return LoaderOutput(md=md, assets=assets, parse_summary=summary, doc_id=doc_id, version_id=version_id)


def _compute_ref_id(url: str, line: int, col: int) -> str:
    key = f"{url}|{line}|{col}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()


def _count_paragraphs(md: str) -> int:
    chunks = re.split(r"\n\s*\n", md)
    return len([c for c in chunks if c.strip()])
