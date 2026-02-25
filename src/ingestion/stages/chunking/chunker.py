from __future__ import annotations

from dataclasses import dataclass

from ....libs.interfaces.splitter import ChunkIR, Chunker, SectionIR
from ....libs.providers.splitter import assign_chunk_ids, chunk_hash


@dataclass
class ChunkerStage:
    chunker: Chunker
    text_norm_profile_id: str = "default"

    def run(self, sections: list[SectionIR]) -> tuple[list[ChunkIR], dict[str, str | int]]:
        chunks = self.chunker.chunk(sections)
        assign_chunk_ids(chunks, text_norm_profile_id=self.text_norm_profile_id)

        stats = {
            "chunk_count": len(chunks),
            "chunk_hash": chunk_hash(chunks),
        }
        return chunks, stats
