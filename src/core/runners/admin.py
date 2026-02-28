from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..strategy import load_settings
from ...ingestion.stages.storage.fs import FsStore
from ...ingestion.stages.storage.fts5 import Fts5Store
from ...ingestion.stages.storage.sqlite import SqliteStore
from ...ingestion.stages.storage.chroma import ChromaStore
from ...libs.providers.vector_store.chroma_lite import ChromaLiteVectorIndex


@dataclass
class DeleteResult:
    status: str  # ok|noop
    mode: str  # soft|hard
    doc_id: str
    version_id: str | None
    affected: dict[str, Any]
    warnings: list[str]


@dataclass
class AdminRunner:
    settings_path: str | Path = "config/settings.yaml"

    def delete_document(
        self,
        *,
        doc_id: str,
        version_id: str | None = None,
        mode: str = "soft",
        dry_run: bool = False,
    ) -> DeleteResult:
        settings = load_settings(self.settings_path)
        sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")
        fts5 = Fts5Store(db_path=settings.paths.sqlite_dir / "fts.sqlite")
        vec = ChromaLiteVectorIndex(db_path=str(settings.paths.chroma_dir / "chroma_lite.sqlite"))
        chroma = ChromaStore(vec)
        fs = FsStore(raw_dir=settings.paths.raw_dir, md_dir=settings.paths.md_dir)

        warnings: list[str] = []
        if mode not in {"soft", "hard"}:
            mode = "soft"
            warnings.append("invalid_mode_fallback_to_soft")

        if mode == "soft":
            if dry_run:
                sqlite_effect = sqlite.preview_delete(doc_id=doc_id, version_id=version_id)
            else:
                sqlite_effect = sqlite.mark_deleted(doc_id=doc_id, version_id=version_id)

            status = "ok" if sqlite_effect.get("versions_marked", 0) > 0 else "noop"
            return DeleteResult(
                status=status,
                mode="soft",
                doc_id=doc_id,
                version_id=version_id,
                affected={"sqlite": sqlite_effect, "chroma": {}, "fts5": {}, "fs": {}},
                warnings=warnings + (["dry_run_preview_only"] if dry_run else []),
            )

        # hard delete
        chunk_ids = sqlite.fetch_chunk_ids(doc_id=doc_id, version_id=version_id)
        asset_ids = sqlite.fetch_asset_ids_by_doc_version(doc_id=doc_id, version_id=version_id)
        file_hashes = sqlite.fetch_doc_version_hashes(doc_id=doc_id, version_id=version_id)

        affected: dict[str, Any] = {"sqlite": {}, "chroma": {}, "fts5": {}, "fs": {}, "assets": {}}

        if dry_run:
            affected["sqlite"] = {
                "chunks": len(chunk_ids),
                "asset_refs": len(asset_ids),
                "versions": len(file_hashes),
            }
            affected["chroma"] = {"vectors": len(chunk_ids)}
            affected["fts5"] = {"docs": len(chunk_ids)}
            affected["fs"] = {"md_files": "n/a", "raw_files": len(file_hashes)}
            return DeleteResult(
                status="ok" if (chunk_ids or file_hashes) else "noop",
                mode="hard",
                doc_id=doc_id,
                version_id=version_id,
                affected=affected,
                warnings=warnings + ["dry_run_preview_only"],
            )

        # 1) remove from vector + fts
        chroma.delete(chunk_ids)
        fts5.delete(chunk_ids)
        affected["chroma"] = {"vectors": len(chunk_ids)}
        affected["fts5"] = {"docs": len(chunk_ids)}

        # 2) sqlite rows
        affected["sqlite"]["chunk_assets"] = sqlite.delete_chunk_assets(chunk_ids)
        affected["sqlite"]["chunks"] = sqlite.delete_chunks(doc_id=doc_id, version_id=version_id)
        affected["sqlite"]["asset_refs"] = sqlite.delete_asset_refs(doc_id=doc_id, version_id=version_id)
        affected["sqlite"]["doc_versions"] = sqlite.delete_doc_versions(doc_id=doc_id, version_id=version_id)
        affected["sqlite"]["documents"] = sqlite.delete_document_if_orphan(doc_id)

        # 3) assets orphan cleanup (best-effort)
        removed_assets = 0
        for aid in asset_ids:
            if sqlite.count_asset_refs(aid) == 0:
                removed_assets += sqlite.delete_assets([aid])
                fs.delete_asset(aid, settings.paths.assets_dir)
        affected["assets"]["deleted"] = removed_assets

        # 4) fs cleanup
        affected["fs"]["md_files"] = fs.delete_md(doc_id, version_id=version_id)
        raw_removed = 0
        for h in file_hashes:
            raw_removed += fs.delete_raw_by_hash(h)
        affected["fs"]["raw_files"] = raw_removed

        status = "ok" if (affected["sqlite"]["chunks"] or affected["sqlite"]["doc_versions"]) else "noop"
        return DeleteResult(
            status=status,
            mode="hard",
            doc_id=doc_id,
            version_id=version_id,
            affected=affected,
            warnings=warnings,
        )

