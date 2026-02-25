from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...interfaces.loader import AssetRef, LoaderOutput, ParseSummary


_TEXT_BLOCK_RE = re.compile(r"BT(.*?)ET", re.DOTALL)
_TJ_RE = re.compile(r"\((.*?)\)\s*Tj", re.DOTALL)
_TJ_ARRAY_RE = re.compile(r"\[(.*?)\]\s*TJ", re.DOTALL)
_OBJ_RE = re.compile(r"(\d+)\s+0\s+obj(.*?)endobj", re.DOTALL)
_PAGE_RE = re.compile(r"/Type\s*/Page(?!s)\b")
_OBJ_REF_RE = re.compile(r"(\d+)\s+0\s+R")


@dataclass
class PdfLoader:
    """Minimal PDF loader: extract text + image refs (best-effort)."""

    def load(self, input_path: str, *, doc_id: str | None = None, version_id: str | None = None) -> LoaderOutput:
        p = Path(input_path)
        raw_bytes = p.read_bytes()

        md, pages, warnings = _extract_text(raw_bytes)
        assets = _extract_image_refs(raw_bytes)

        summary = ParseSummary(
            pages=pages,
            paragraphs=_count_paragraphs(md),
            images=len(assets),
            text_chars=len(md),
            warnings=warnings,
            errors=None,
        )

        return LoaderOutput(md=md, assets=assets, parse_summary=summary, doc_id=doc_id, version_id=version_id)


def _extract_text(raw: bytes) -> tuple[str, int | None, list[str]]:
    warnings: list[str] = []
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(raw)
        texts: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            if text:
                texts.append(text)
        md = "\n\n".join(t.strip() for t in texts if t.strip())
        pages = len(reader.pages)
        return md, pages, warnings
    except Exception:
        warnings.append("pdf_text_fallback")

    decoded = raw.decode("latin1", errors="ignore")
    blocks = _TEXT_BLOCK_RE.findall(decoded)
    segments: list[str] = []
    for block in blocks:
        for m in _TJ_RE.finditer(block):
            segments.append(_unescape_pdf_string(m.group(1)))
        for m in _TJ_ARRAY_RE.finditer(block):
            arr = m.group(1)
            for m2 in re.finditer(r"\((.*?)\)", arr, re.DOTALL):
                segments.append(_unescape_pdf_string(m2.group(1)))
    md = "\n".join(s for s in segments if s.strip())
    pages = _estimate_pages(decoded)
    return md, pages, warnings


def _extract_image_refs(raw: bytes) -> list[AssetRef]:
    decoded = raw.decode("latin1", errors="ignore")
    assets: list[AssetRef] = []
    page_refs: list[set[int]] = []
    image_objs: list[int] = []

    for obj_num, body in _OBJ_RE.findall(decoded):
        if _PAGE_RE.search(body):
            refs = {int(m) for m in _OBJ_REF_RE.findall(body)}
            page_refs.append(refs)

        if "/Subtype /Image" not in body:
            continue
        image_objs.append(int(obj_num))

    for obj_num in image_objs:
        page = _find_page_for_obj(obj_num, page_refs)
        origin_ref = f"pdf_obj:{obj_num}"
        ref_id = _hash(origin_ref)
        anchor: dict[str, Any] = {"obj": obj_num}
        if page is not None:
            anchor["page"] = page
        assets.append(
            AssetRef(
                ref_id=ref_id,
                source_type="pdf",
                origin_ref=origin_ref,
                anchor=anchor,
                context_hint=None,
            )
        )
    return assets


def _estimate_pages(decoded: str) -> int | None:
    matches = re.findall(r"/Type\s*/Page(?!s)\b", decoded)
    if not matches:
        return None
    return len(matches)


def _find_page_for_obj(obj_num: int, page_refs: list[set[int]]) -> int | None:
    for idx, refs in enumerate(page_refs, start=1):
        if obj_num in refs:
            return idx
    return None


def _unescape_pdf_string(s: str) -> str:
    return (
        s.replace("\\\\", "\\")
        .replace("\\(", "(")
        .replace("\\)", ")")
        .replace("\\n", "\n")
        .replace("\\r", "\r")
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _count_paragraphs(md: str) -> int:
    chunks = re.split(r"\n\s*\n", md)
    return len([c for c in chunks if c.strip()])
