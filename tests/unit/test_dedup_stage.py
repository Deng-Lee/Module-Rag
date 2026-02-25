from __future__ import annotations

from pathlib import Path

from src.ingestion.stages.receive.dedup import DedupStage
from src.ingestion.stages.storage.fs import FsStore
from src.ingestion.stages.storage.sqlite import SqliteStore


def _write_tmp(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def test_dedup_skip_policy(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    db_path = tmp_path / "ingest.db"

    fs = FsStore(raw_dir=raw_dir)
    store = SqliteStore(db_path=db_path)
    stage = DedupStage(fs_store=fs, sqlite_store=store)

    f = _write_tmp(tmp_path, "a.md", b"hello")

    first = stage.run(f, policy="skip")
    assert first.decision == "continue"
    assert store.count_versions() == 1

    second = stage.run(f, policy="skip")
    assert second.decision == "skip"
    assert second.doc_id == first.doc_id
    assert second.version_id == first.version_id
    assert store.count_versions() == 1


def test_dedup_new_version_policy(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    db_path = tmp_path / "ingest.db"

    fs = FsStore(raw_dir=raw_dir)
    store = SqliteStore(db_path=db_path)
    stage = DedupStage(fs_store=fs, sqlite_store=store)

    f = _write_tmp(tmp_path, "a.md", b"hello")

    first = stage.run(f, policy="skip")
    second = stage.run(f, policy="new_version")

    assert second.decision == "new_version"
    assert second.doc_id == first.doc_id
    assert second.version_id != first.version_id
    assert store.count_versions(first.doc_id) == 2
