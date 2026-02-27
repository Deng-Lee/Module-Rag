from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.ingestion import IngestionPipeline, StageSpec
from src.ingestion.stages.chunking.chunker import ChunkerStage
from src.ingestion.stages.chunking.sectioner import SectionerStage
from src.ingestion.stages.embedding.embedding import EmbeddingStage, EncodingStrategy
from src.ingestion.stages.receive.dedup import DedupDecision, DedupStage
from src.ingestion.stages.receive.loader import LoaderStage
from src.ingestion.stages.storage.assets import AssetStore
from src.ingestion.stages.storage.fs import FsStore
from src.ingestion.stages.storage.fts5 import Fts5Store
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.ingestion.stages.storage.upsert import UpsertResult, UpsertStage
from src.ingestion.stages.transform.asset_normalize import FsAssetNormalizer
from src.ingestion.stages.transform.transform_post import TransformPostStage
from src.ingestion.stages.transform.transform_pre import DefaultTransformPre, TransformPreStage
from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.loader.markdown_loader import MarkdownLoader
from src.libs.providers.splitter.markdown_headings import MarkdownHeadingsSectioner
from src.libs.providers.splitter.recursive_chunker import RecursiveCharChunkerWithinSection
from src.libs.providers.vector_store.chroma_lite import ChromaLiteVectorIndex


@dataclass
class _IngestState:
    input_path: Path
    policy: str

    dedup: DedupDecision | None = None
    skipped: bool = False

    md: str | None = None
    loader_assets: list[Any] | None = None
    normalized_assets: Any | None = None  # NormalizedAssets
    md_norm: str | None = None

    sections: Any | None = None  # list[SectionIR]
    chunks: Any | None = None  # list[ChunkIR]
    encoded: Any | None = None  # EncodedChunks

    upsert: UpsertResult | None = None

    @property
    def doc_id(self) -> str:
        assert self.dedup is not None
        return self.dedup.doc_id

    @property
    def version_id(self) -> str:
        assert self.dedup is not None
        return self.dedup.version_id


def _build_ingest_pipeline(
    *,
    fs_store: FsStore,
    sqlite_store: SqliteStore,
    assets_dir: Path,
    fts5: Fts5Store,
    vector_index: ChromaLiteVectorIndex,
) -> IngestionPipeline:
    dedup = DedupStage(fs_store=fs_store, sqlite_store=sqlite_store)
    loader = LoaderStage(loaders={"md": MarkdownLoader()})
    normalizer = FsAssetNormalizer(asset_store=AssetStore(assets_dir=assets_dir))
    transform_pre = TransformPreStage(transformer=DefaultTransformPre(profile_id="default"))
    sectioner = SectionerStage(sectioner=MarkdownHeadingsSectioner())
    chunker = ChunkerStage(
        chunker=RecursiveCharChunkerWithinSection(chunk_size=800, chunk_overlap=120),
        text_norm_profile_id="default",
    )
    transform_post = TransformPostStage()
    embedding = EmbeddingStage(
        embedder=FakeEmbedder(dim=8),
        embedder_id="embedder.fake",
        embedder_version="0",
    )
    upsert = UpsertStage(
        fs=fs_store,
        sqlite=sqlite_store,
        vector_index=vector_index,
        fts5=fts5,
        assets_dir=assets_dir,
    )

    def st_dedup(state: _IngestState, ctx) -> _IngestState:
        dec = dedup.run(state.input_path, policy=state.policy)  # type: ignore[arg-type]
        state.dedup = dec
        state.skipped = dec.decision == "skip"
        return state

    def st_loader(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert state.dedup is not None
        out = loader.run(state.dedup.raw_path, doc_id=state.doc_id, version_id=state.version_id)
        state.md = out.md
        state.loader_assets = out.assets
        return state

    def st_asset_normalize(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert state.dedup is not None and state.md is not None and state.loader_assets is not None
        state.normalized_assets = normalizer.normalize(
            state.loader_assets, raw_path=str(state.dedup.raw_path), md=state.md
        )
        return state

    def st_transform_pre(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert state.md is not None
        state.md_norm = transform_pre.run(state.md, state.normalized_assets)
        return state

    def st_sectioner(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert state.md_norm is not None
        sections, _ = sectioner.run(state.md_norm, doc_id=state.doc_id)
        state.sections = sections
        return state

    def st_chunker(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert state.sections is not None
        chunks, _ = chunker.run(state.sections)
        for c in chunks:
            c.metadata["doc_id"] = state.doc_id
            c.metadata["version_id"] = state.version_id
        state.chunks = chunks
        return state

    def st_transform_post(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert state.chunks is not None
        state.chunks = transform_post.run(state.chunks)
        return state

    def st_embedding(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert state.chunks is not None
        state.encoded = embedding.run(state.chunks, EncodingStrategy(mode="hybrid"))
        return state

    def st_upsert(state: _IngestState, ctx) -> _IngestState:
        if state.skipped:
            return state
        assert (
            state.md_norm is not None
            and state.loader_assets is not None
            and state.normalized_assets is not None
            and state.sections is not None
            and state.chunks is not None
            and state.encoded is not None
        )
        state.upsert = upsert.run(
            doc_id=state.doc_id,
            version_id=state.version_id,
            md_norm=state.md_norm,
            loader_assets=state.loader_assets,
            normalized_assets=state.normalized_assets,
            sections=state.sections,
            chunks=state.chunks,
            encoded=state.encoded,
        )
        return state

    stages = [
        StageSpec(name="dedup", fn=st_dedup),
        StageSpec(name="loader", fn=st_loader),
        StageSpec(name="asset_normalize", fn=st_asset_normalize),
        StageSpec(name="transform_pre", fn=st_transform_pre),
        StageSpec(name="sectioner", fn=st_sectioner),
        StageSpec(name="chunker", fn=st_chunker),
        StageSpec(name="transform_post", fn=st_transform_post),
        StageSpec(name="embedding", fn=st_embedding),
        StageSpec(name="upsert", fn=st_upsert),
    ]
    return IngestionPipeline(stages)


def run_ingest_fixture(
    *,
    input_path: Path,
    policy: str,
    fs_store: FsStore,
    sqlite_store: SqliteStore,
    assets_dir: Path,
    fts5: Fts5Store,
    vector_index: ChromaLiteVectorIndex,
    strategy_config_id: str = "local.default",
) -> tuple[_IngestState, str]:
    pipeline = _build_ingest_pipeline(
        fs_store=fs_store,
        sqlite_store=sqlite_store,
        assets_dir=assets_dir,
        fts5=fts5,
        vector_index=vector_index,
    )
    state = _IngestState(input_path=input_path, policy=policy)
    result = pipeline.run(state, strategy_config_id=strategy_config_id)
    assert result.trace_id
    assert result.status == "ok"
    assert isinstance(result.output, _IngestState)
    return result.output, result.trace_id


@pytest.mark.integration
def test_ingest_pipeline_e2e_skip_is_idempotent(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    md_dir = data_dir / "md"
    assets_dir = data_dir / "assets"
    sqlite_dir = data_dir / "sqlite"
    chroma_dir = data_dir / "chroma"

    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
    tpl = (fixtures_dir / "docs" / "sample.md").read_text(encoding="utf-8")
    img_src = fixtures_dir / "assets" / "sample.svg"
    img_path = tmp_path / "sample.svg"
    img_path.write_bytes(img_src.read_bytes())

    md_path = tmp_path / "doc.md"
    md_path.write_text(tpl.replace("{{IMG_PATH}}", img_path.as_posix()), encoding="utf-8")

    fs_store = FsStore(raw_dir=raw_dir, md_dir=md_dir)
    sqlite_store = SqliteStore(db_path=sqlite_dir / "app.sqlite")
    fts5 = Fts5Store(db_path=sqlite_dir / "fts.sqlite")
    vector_index = ChromaLiteVectorIndex(db_path=str(chroma_dir / "chroma_lite.sqlite"))

    # First ingest builds the baseline (FS + SQLite + Dense + Sparse).
    st1, trace1 = run_ingest_fixture(
        input_path=md_path,
        policy="skip",
        fs_store=fs_store,
        sqlite_store=sqlite_store,
        assets_dir=assets_dir,
        fts5=fts5,
        vector_index=vector_index,
    )
    assert st1.upsert is not None
    assert st1.upsert.md_path.exists()
    assert vector_index.count() == st1.upsert.dense_written
    assert fts5.query("unicorn", top_k=5)

    # Second ingest with the same file + policy=skip should short-circuit and not create new versions.
    st2, trace2 = run_ingest_fixture(
        input_path=md_path,
        policy="skip",
        fs_store=fs_store,
        sqlite_store=sqlite_store,
        assets_dir=assets_dir,
        fts5=fts5,
        vector_index=vector_index,
    )
    assert st2.skipped is True
    assert st2.upsert is None
    assert sqlite_store.count_versions(doc_id=st1.doc_id) == 1
    assert vector_index.count() == st1.upsert.dense_written

    # trace_id should differ per run, but doc/version should be stable for skip.
    assert trace1 != trace2
    assert st1.doc_id == st2.doc_id
    assert st1.version_id == st2.version_id


@pytest.mark.integration
def test_ingest_pipeline_e2e_new_version_creates_version_row(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    md_dir = data_dir / "md"
    assets_dir = data_dir / "assets"
    sqlite_dir = data_dir / "sqlite"
    chroma_dir = data_dir / "chroma"

    md_path = tmp_path / "doc.md"
    md_path.write_text("# Title\n\nRepeatable content.\n", encoding="utf-8")

    fs_store = FsStore(raw_dir=raw_dir, md_dir=md_dir)
    sqlite_store = SqliteStore(db_path=sqlite_dir / "app.sqlite")
    fts5 = Fts5Store(db_path=sqlite_dir / "fts.sqlite")
    vector_index = ChromaLiteVectorIndex(db_path=str(chroma_dir / "chroma_lite.sqlite"))

    st1, _ = run_ingest_fixture(
        input_path=md_path,
        policy="skip",
        fs_store=fs_store,
        sqlite_store=sqlite_store,
        assets_dir=assets_dir,
        fts5=fts5,
        vector_index=vector_index,
    )
    assert sqlite_store.count_versions(doc_id=st1.doc_id) == 1

    st2, _ = run_ingest_fixture(
        input_path=md_path,
        policy="new_version",
        fs_store=fs_store,
        sqlite_store=sqlite_store,
        assets_dir=assets_dir,
        fts5=fts5,
        vector_index=vector_index,
    )
    assert st2.doc_id == st1.doc_id
    assert st2.version_id != st1.version_id
    assert sqlite_store.count_versions(doc_id=st1.doc_id) == 2
