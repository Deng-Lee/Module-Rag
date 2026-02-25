from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ....libs.interfaces.splitter import ChunkIR
from .retrieval_view import RetrievalViewConfig, build_chunk_retrieval_text


class Enricher(Protocol):
    """Optional provider that adds retrieval-only enrichment snippets."""

    def enrich(self, chunk: ChunkIR) -> dict[str, Any]:
        ...


@dataclass
class NoopEnricher(Enricher):
    def enrich(self, chunk: ChunkIR) -> dict[str, Any]:  # pragma: no cover
        _ = chunk
        return {}


@dataclass
class TransformPostStage:
    view_cfg: RetrievalViewConfig = RetrievalViewConfig()
    enrichers: list[Enricher] | None = None

    def run(self, chunks: list[ChunkIR]) -> list[ChunkIR]:
        """Attach `chunk_retrieval_text` into chunk.metadata.

        Does not modify `chunk.text`.
        """

        enrichers = self.enrichers or []

        for chunk in chunks:
            enrichments: dict[str, Any] = {}
            for enr in enrichers:
                payload = enr.enrich(chunk)
                if not isinstance(payload, dict):
                    continue
                for k, v in payload.items():
                    # last-write-wins for same key; providers should namespace keys.
                    enrichments[k] = v

            heading_text = None
            if self.view_cfg.include_heading_text:
                # Best-effort: section_path is a key; treat as a heading-like hint.
                heading_text = chunk.metadata.get("section_path") if isinstance(chunk.metadata, dict) else None
                if not isinstance(heading_text, str):
                    heading_text = None

            retrieval_text = build_chunk_retrieval_text(
                chunk.text,
                template_id=self.view_cfg.template_id,
                enrichments=enrichments,
                heading_text=heading_text,
            )

            chunk.metadata["chunk_retrieval_text"] = retrieval_text
            chunk.metadata["retrieval_template_id"] = self.view_cfg.template_id
            chunk.metadata["enrich_keys"] = sorted(enrichments.keys())

        return chunks
