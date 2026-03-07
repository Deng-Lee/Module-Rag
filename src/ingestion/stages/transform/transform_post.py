from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Protocol

from ....libs.interfaces.splitter import ChunkIR
from ....ingestion.stages.storage.sqlite import SqliteStore
from .retrieval_view import RetrievalViewConfig, build_chunk_retrieval_text


class Enricher(Protocol):
    """Optional provider that adds retrieval-only enrichment snippets."""

    def enrich(self, chunk: ChunkIR) -> dict[str, Any]:
        ...


@dataclass
class TransformPostStage:
    view_cfg: RetrievalViewConfig = RetrievalViewConfig()
    enrichers: list[Enricher] | None = None
    sqlite: SqliteStore | None = None

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

                # Sidecar persistence for vision enrichments (best-effort).
                if self.sqlite is not None:
                    provider_id = getattr(enr, "provider_id", enr.__class__.__name__)
                    model = getattr(enr, "model", "")
                    profile_id = getattr(enr, "profile_id", "default")
                    try:
                        vision_assets = payload.get("vision_assets")
                        if isinstance(vision_assets, list):
                            for item in vision_assets:
                                if not isinstance(item, dict):
                                    continue
                                asset_id = item.get("asset_id")
                                if not isinstance(asset_id, str) or not asset_id:
                                    continue
                                ocr_text = item.get("ocr_text")
                                caption_text = item.get("caption")
                                raw_json = None
                                raw = item.get("raw")
                                if raw is not None:
                                    raw_json = json.dumps(raw, ensure_ascii=True)
                                self.sqlite.upsert_asset_enrichment(
                                    asset_id=asset_id,
                                    provider_id=str(provider_id),
                                    model=str(model),
                                    profile_id=str(profile_id),
                                    ocr_text=str(ocr_text) if isinstance(ocr_text, str) else None,
                                    caption_text=str(caption_text) if isinstance(caption_text, str) else None,
                                    raw_json=raw_json,
                                )

                        vision_snippets = payload.get("vision_snippets")
                        if isinstance(vision_snippets, list):
                            vs_json = json.dumps(vision_snippets, ensure_ascii=True)
                            self.sqlite.upsert_chunk_enrichment(
                                chunk_id=chunk.chunk_id,
                                provider_id=str(provider_id),
                                model=str(model),
                                profile_id=str(profile_id),
                                retrieval_template_id=self.view_cfg.template_id,
                                vision_snippets_json=vs_json,
                            )
                    except Exception:
                        # Best-effort only; avoid breaking ingestion on enrichment sidecar issues.
                        pass

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
