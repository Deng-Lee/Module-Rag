from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field

from ...interfaces.splitter import ChunkIR, Chunker, SectionIR


_ASSET_URI_RE = re.compile(r"asset://([0-9a-fA-F]{16,64})")


@dataclass
class RecursiveCharChunkerWithinSection(Chunker):
    """Recursive character splitter within section (RCTS-like, no external deps).

    Splits text by a list of separators (largest to smallest) recursively, then
    merges pieces into chunks of `chunk_size` with `chunk_overlap`.
    """

    chunk_size: int = 800
    chunk_overlap: int = 120
    separators: list[str] = field(default_factory=lambda: ["\n\n", "\n", " ", ""])

    def chunk(self, sections: list[SectionIR]) -> list[ChunkIR]:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        if not self.separators:
            raise ValueError("separators must not be empty")

        chunks: list[ChunkIR] = []
        for section in sections:
            pieces = _recursive_split(section.text, self.separators, self.chunk_size)
            section_chunks = _merge_pieces(
                pieces,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )

            chunk_index = 0
            for text in section_chunks:
                chunk_index += 1
                meta = {
                    "section_id": section.section_id,
                    "chunk_index": chunk_index,
                    "section_path": section.section_path,
                }
                asset_ids = _extract_asset_ids(text)
                if asset_ids:
                    meta["asset_ids"] = asset_ids

                chunks.append(ChunkIR(chunk_id="", section_path=section.section_path, text=text, metadata=meta))

        return chunks


def assign_chunk_ids(chunks: list[ChunkIR], *, text_norm_profile_id: str = "default") -> list[ChunkIR]:
    for c in chunks:
        section_id = c.metadata.get("section_id")
        if not isinstance(section_id, str) or not section_id:
            raise ValueError("chunk missing section_id")

        canonical_text = canonical(c.text, profile_id=text_norm_profile_id)
        fingerprint = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
        key = f"{section_id}|{fingerprint}".encode("utf-8")
        c.chunk_id = "chk_" + hashlib.sha256(key).hexdigest()
        c.metadata["chunk_fingerprint"] = fingerprint
        c.metadata["text_norm_profile_id"] = text_norm_profile_id

    return chunks


def canonical(text: str, *, profile_id: str = "default") -> str:
    _ = profile_id

    if text.startswith("\ufeff"):
        text = text[1:]

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    out_chars: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in {"Cc", "Cf"} and ch not in {"\n", "\t"}:
            continue
        out_chars.append(ch)
    text = "".join(out_chars)

    lines = [ln.rstrip(" \t") for ln in text.split("\n")]
    return "\n".join(lines).strip("\n")


def chunk_hash(chunks: list[ChunkIR]) -> str:
    acc = hashlib.sha256()
    for c in chunks:
        fp = c.metadata.get("chunk_fingerprint")
        if isinstance(fp, str):
            acc.update(fp.encode("utf-8"))
            acc.update(b"\n")
    return acc.hexdigest()


def _recursive_split(text: str, seps: list[str], chunk_size: int) -> list[str]:
    text = text.strip("\n")
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    if not seps:
        return _hard_split(text, chunk_size)

    sep = seps[0]
    if sep == "":
        return _hard_split(text, chunk_size)

    parts = text.split(sep)
    # Keep separator attached to preserve boundaries.
    candidates: list[str] = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:
            candidates.append(part + sep)
        else:
            candidates.append(part)

    out: list[str] = []
    for cand in candidates:
        if not cand:
            continue
        if len(cand) <= chunk_size:
            out.append(cand)
        else:
            out.extend(_recursive_split(cand, seps[1:], chunk_size))
    return out


def _merge_pieces(pieces: list[str], *, chunk_size: int, chunk_overlap: int) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        text = "".join(buf).strip("\n")
        if text:
            out.append(text)

        if chunk_overlap > 0 and text:
            tail = text[-chunk_overlap:]
            buf = [tail]
            buf_len = len(tail)
        else:
            buf = []
            buf_len = 0

    for p in pieces:
        p = p
        if not p:
            continue
        if buf_len + len(p) <= chunk_size:
            buf.append(p)
            buf_len += len(p)
            continue

        flush()
        if len(p) > chunk_size:
            # Should not happen due to recursive split, but guard.
            for s in _hard_split(p, chunk_size):
                out.append(s)
            buf = []
            buf_len = 0
        else:
            buf = [p]
            buf_len = len(p)

    flush()
    return out


def _hard_split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _extract_asset_ids(text: str) -> list[str]:
    return [m.group(1) for m in _ASSET_URI_RE.finditer(text)]
