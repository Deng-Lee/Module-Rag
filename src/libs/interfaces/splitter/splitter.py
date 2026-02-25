from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SectionIR:
    section_id: str
    section_path: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkIR:
    chunk_id: str
    section_path: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Sectioner(Protocol):
    def section(self, md_norm: str) -> list[SectionIR]:
        ...


class Chunker(Protocol):
    def chunk(self, sections: list[SectionIR]) -> list[ChunkIR]:
        ...
