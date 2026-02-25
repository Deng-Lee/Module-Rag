from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from ...interfaces.splitter import ChunkIR, Chunker, SectionIR


_ASSET_URI_RE = re.compile(r"asset://([0-9a-fA-F]{16,64})")


@dataclass
class SimpleCharChunkerWithinSection(Chunker):
    """Chunk text within each section by approximate character length."""

    chunk_size: int = 800
    chunk_overlap: int = 120

    def chunk(self, sections: list[SectionIR]) -> list[ChunkIR]:
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be non-negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")

        chunks: list[ChunkIR] = []
        for section in sections:
            parts = _split_paragraphs(section.text)
            buf: list[str] = []
            buf_len = 0
            chunk_index = 0

            def flush() -> None:
                nonlocal buf, buf_len, chunk_index
                if not buf:
                    return
                chunk_index += 1
                text = "\n\n".join(buf).strip("\n")
                meta = {
                    "section_id": section.section_id,
                    "chunk_index": chunk_index,
                    "section_path": section.section_path,
                }
                asset_ids = _extract_asset_ids(text)
                if asset_ids:
                    meta["asset_ids"] = asset_ids
                chunks.append(ChunkIR(chunk_id="", section_path=section.section_path, text=text, metadata=meta))

                if self.chunk_overlap > 0:
                    tail = text[-self.chunk_overlap :]
                    buf = [tail]
                    buf_len = len(tail)
                else:
                    buf = []
                    buf_len = 0

            for part in parts:
                part = part.strip("\n")
                if not part:
                    continue

                extra = len(part) + (2 if buf else 0)
                if buf_len + extra <= self.chunk_size:
                    buf.append(part)
                    buf_len += extra
                    continue

                flush()

                if len(part) > self.chunk_size:
                    for piece in _hard_split(part, self.chunk_size, self.chunk_overlap):
                        chunk_index += 1
                        meta = {
                            "section_id": section.section_id,
                            "chunk_index": chunk_index,
                            "section_path": section.section_path,
                        }
                        asset_ids = _extract_asset_ids(piece)
                        if asset_ids:
                            meta["asset_ids"] = asset_ids
                        chunks.append(ChunkIR(chunk_id="", section_path=section.section_path, text=piece, metadata=meta))
                    buf = []
                    buf_len = 0
                else:
                    buf = [part]
                    buf_len = len(part)

            flush()

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


def _split_paragraphs(text: str) -> list[str]:
    return re.split(r"\n\s*\n", text)


def _hard_split(text: str, size: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    step = max(1, size - overlap)
    i = 0
    while i < len(text):
        pieces.append(text[i : i + size])
        i += step
    return pieces


def _extract_asset_ids(text: str) -> list[str]:
    return [m.group(1) for m in _ASSET_URI_RE.finditer(text)]
