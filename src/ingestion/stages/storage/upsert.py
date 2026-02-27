from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....libs.interfaces.loader import AssetRef, NormalizedAssets
from ....libs.interfaces.splitter import ChunkIR, SectionIR
from ....libs.interfaces.vector_store import VectorIndex
from ..embedding.models import EncodedChunks
from .chroma import ChromaStore
from .fts5 import Fts5Store
from .fs import FsStore
from .sqlite import SqliteStore


@dataclass
class UpsertResult:
    md_path: Path
    assets_written: int
    chunks_written: int
    dense_written: int
    sparse_written: int


@dataclass
class UpsertStage:
    fs: FsStore
    sqlite: SqliteStore
    vector_index: VectorIndex
    fts5: Fts5Store
    assets_dir: Path

    def run(
        self,
        *,
        doc_id: str,
        version_id: str,
        md_norm: str,
        loader_assets: list[AssetRef],
        normalized_assets: NormalizedAssets,
        sections: list[SectionIR],
        chunks: list[ChunkIR],
        encoded: EncodedChunks,
    ) -> UpsertResult:
        md_path = self.fs.write_md(doc_id, version_id, md_norm)

        # assets + refs
        assets_written = 0
        for ref_id, asset_id in normalized_assets.ref_to_asset_id.items():
            rel_path = _find_asset_rel_path(self.assets_dir, asset_id)
            self.sqlite.upsert_asset(asset_id, rel_path)
            if rel_path is not None:
                assets_written += 1

        for a in loader_assets:
            asset_id = normalized_assets.ref_to_asset_id.get(a.ref_id)
            if not asset_id:
                continue
            self.sqlite.upsert_asset_ref(
                ref_id=a.ref_id,
                asset_id=asset_id,
                doc_id=doc_id,
                version_id=version_id,
                source_type=a.source_type,
                origin_ref=a.origin_ref,
                anchor_json=json.dumps(a.anchor, separators=(",", ":")),
            )

        # chunks
        chunks_written = 0
        chunk_assets: list[tuple[str, str]] = []
        for c in chunks:
            section_id = c.metadata.get("section_id")
            if not isinstance(section_id, str):
                section_id = ""
            chunk_index = c.metadata.get("chunk_index")
            if not isinstance(chunk_index, int):
                chunk_index = 0

            self.sqlite.upsert_chunk(
                chunk_id=c.chunk_id,
                doc_id=doc_id,
                version_id=version_id,
                section_id=section_id,
                section_path=c.section_path,
                chunk_index=chunk_index,
                chunk_text=c.text,
            )
            chunks_written += 1

            asset_ids = c.metadata.get("asset_ids")
            if isinstance(asset_ids, list):
                for aid in asset_ids:
                    if isinstance(aid, str) and aid:
                        chunk_assets.append((c.chunk_id, aid))

        for chunk_id, asset_id in chunk_assets:
            self.sqlite.upsert_chunk_asset(chunk_id=chunk_id, asset_id=asset_id)

        # dense vectors
        dense_written = 0
        if encoded.dense is not None:
            ChromaStore(self.vector_index).upsert(encoded.dense.items)
            dense_written = len(encoded.dense.items)

        # sparse docs -> FTS5
        sparse_written = 0
        if encoded.sparse is not None:
            docs = [(d.chunk_id, d.text) for d in encoded.sparse.docs]
            self.fts5.upsert(docs)
            sparse_written = len(docs)

        self.sqlite.set_version_status(version_id, "indexed")

        return UpsertResult(
            md_path=md_path,
            assets_written=assets_written,
            chunks_written=chunks_written,
            dense_written=dense_written,
            sparse_written=sparse_written,
        )


def _find_asset_rel_path(assets_dir: Path, asset_id: str) -> str | None:
    # Find the first file with prefix asset_id.
    matches = list(assets_dir.glob(f"{asset_id}.*"))
    if not matches:
        return None
    try:
        return str(matches[0].relative_to(assets_dir))
    except Exception:
        return matches[0].name
