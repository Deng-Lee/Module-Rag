from __future__ import annotations

from pathlib import Path

from src.ingestion import IngestionPipeline, StageSpec
from src.ingestion.stages.receive.dedup import DedupStage
from src.ingestion.stages.storage.fs import FsStore
from src.ingestion.stages.storage.sqlite import SqliteStore


def test_ingest_trace_replay_keys_file_hash(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    md_dir = data_dir / "md"
    sqlite_dir = data_dir / "sqlite"

    sample = tmp_path / "doc.txt"
    sample.write_text("hello replay", encoding="utf-8")

    fs_store = FsStore(raw_dir=raw_dir, md_dir=md_dir)
    sqlite_store = SqliteStore(db_path=sqlite_dir / "app.sqlite")
    dedup = DedupStage(fs_store=fs_store, sqlite_store=sqlite_store)

    def st_dedup(state_path, ctx):
        return dedup.run(state_path, policy="skip")

    pipeline = IngestionPipeline([StageSpec(name="dedup", fn=st_dedup)])
    result = pipeline.run(sample, strategy_config_id="local.default")

    assert result.trace is not None
    assert result.trace.replay.get("file_sha256")
