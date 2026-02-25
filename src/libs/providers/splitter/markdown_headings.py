from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ...interfaces.splitter import SectionIR, Sectioner


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass
class MarkdownHeadingsSectioner(Sectioner):
    """Section Markdown by headings (best-effort)."""

    max_section_level: int = 2
    include_heading: bool = True
    doc_preamble_mode: str = "separate"  # separate|merge_into_first|drop

    def section(self, md_norm: str) -> list[SectionIR]:
        lines = md_norm.splitlines()

        sections: list[SectionIR] = []
        path_stack: list[tuple[int, str]] = []
        buf: list[str] = []
        cur_level = 0
        cur_start = 1
        ordinal = 0

        def section_path() -> str:
            titles = [t for _, t in path_stack]
            return " / ".join(titles) if titles else "__preamble__"

        def flush(end_line: int) -> None:
            nonlocal buf, cur_level, cur_start, ordinal
            text = "\n".join(buf).strip("\n")
            if text.strip() == "":
                buf = []
                return
            ordinal += 1
            meta = {
                "heading_level": cur_level,
                "ordinal": ordinal,
                "line_range": [cur_start, end_line],
            }
            sections.append(
                SectionIR(
                    section_id="",
                    section_path=section_path(),
                    text=text,
                    metadata=meta,
                )
            )
            buf = []

        for idx, line in enumerate(lines, start=1):
            m = _HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                if level <= self.max_section_level:
                    flush(idx - 1)

                    while path_stack and path_stack[-1][0] >= level:
                        path_stack.pop()
                    path_stack.append((level, title))

                    cur_level = level
                    cur_start = idx
                    if self.include_heading:
                        buf.append(line)
                    continue

            buf.append(line)

        flush(len(lines))

        # preamble behavior
        if sections and sections[0].section_path == "__preamble__":
            if self.doc_preamble_mode == "drop":
                sections = sections[1:]
            elif self.doc_preamble_mode == "merge_into_first" and len(sections) >= 2:
                pre = sections[0]
                nxt = sections[1]
                merged = (pre.text.rstrip("\n") + "\n\n" + nxt.text.lstrip("\n")).strip("\n")
                nxt.text = merged
                lr = pre.metadata.get("line_range")
                if isinstance(lr, list) and len(lr) == 2:
                    nxt.metadata["line_range"] = [lr[0], nxt.metadata.get("line_range", [lr[0], lr[0]])[1]]
                sections = sections[1:]

        return sections


def assign_section_ids(doc_id: str, sections: list[SectionIR]) -> list[SectionIR]:
    for s in sections:
        ordinal = s.metadata.get("ordinal")
        if not isinstance(ordinal, int):
            raise ValueError("section missing ordinal")
        key = f"{doc_id}|{s.section_path}|{ordinal}".encode("utf-8")
        s.section_id = "sec_" + hashlib.sha256(key).hexdigest()
    return sections


def section_hash(sections: list[SectionIR]) -> str:
    acc = hashlib.sha256()
    for s in sections:
        text_fp = hashlib.sha256(s.text.encode("utf-8")).hexdigest()
        acc.update(text_fp.encode("utf-8"))
        acc.update(b"\n")
    return acc.hexdigest()
