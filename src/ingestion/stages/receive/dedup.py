from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ....observability.obs import api as obs
from ....observability.trace.context import TraceContext
from ..storage.fs import FsStore
from ..storage.sqlite import SqliteStore, new_doc_id, new_version_id


Decision = Literal["skip", "new_version", "continue"]


@dataclass
class DedupDecision:
    decision: Decision
    doc_id: str
    version_id: str
    file_sha256: str
    raw_path: Path


@dataclass
class DedupStage:
    fs_store: FsStore
    sqlite_store: SqliteStore

    def run(self, file_path: str | Path, policy: Decision = "skip") -> DedupDecision:
        p = Path(file_path)
        file_sha256, raw_path = self.fs_store.write_stream_and_hash(p)

        # replay keys for observability/replay
        ctx = TraceContext.current()
        if ctx is not None:
            ctx.replay_keys["file_sha256"] = file_sha256

        found = self.sqlite_store.find_version_by_file_hash(file_sha256)
        if found is not None:
            doc_id, version_id = found
            if policy == "skip":
                obs.event(
                    "ingest.dedup_decision",
                    {"doc_id": doc_id, "version_id": version_id, "file_sha256": file_sha256, "decision": "skip"},
                )
                return DedupDecision(
                    decision="skip",
                    doc_id=doc_id,
                    version_id=version_id,
                    file_sha256=file_sha256,
                    raw_path=raw_path,
                )
            if policy == "new_version":
                new_ver = new_version_id()
                self.sqlite_store.upsert_doc_version_minimal(
                    doc_id=doc_id,
                    version_id=new_ver,
                    file_sha256=file_sha256,
                    status="pending",
                )
                obs.event(
                    "ingest.dedup_decision",
                    {"doc_id": doc_id, "version_id": new_ver, "file_sha256": file_sha256, "decision": "new_version"},
                )
                return DedupDecision(
                    decision="new_version",
                    doc_id=doc_id,
                    version_id=new_ver,
                    file_sha256=file_sha256,
                    raw_path=raw_path,
                )
            return DedupDecision(
                decision="continue",
                doc_id=doc_id,
                version_id=version_id,
                file_sha256=file_sha256,
                raw_path=raw_path,
            )

        doc_id = new_doc_id()
        version_id = new_version_id()
        self.sqlite_store.upsert_doc_version_minimal(
            doc_id=doc_id,
            version_id=version_id,
            file_sha256=file_sha256,
            status="pending",
        )
        obs.event(
            "ingest.dedup_decision",
            {"doc_id": doc_id, "version_id": version_id, "file_sha256": file_sha256, "decision": "continue"},
        )
        return DedupDecision(
            decision="continue",
            doc_id=doc_id,
            version_id=version_id,
            file_sha256=file_sha256,
            raw_path=raw_path,
        )
