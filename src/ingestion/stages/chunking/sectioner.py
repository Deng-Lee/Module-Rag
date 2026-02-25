from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.splitter import SectionIR, Sectioner
from ....libs.providers.splitter import assign_section_ids, section_hash


@dataclass
class SectionerStage:
    sectioner: Sectioner

    def run(self, md_norm: str, *, doc_id: str) -> tuple[list[SectionIR], dict[str, str | int]]:
        sections = self.sectioner.section(md_norm)
        assign_section_ids(doc_id, sections)

        stats = {
            "section_count": len(sections),
            "section_hash": section_hash(sections),
        }
        return sections, stats
