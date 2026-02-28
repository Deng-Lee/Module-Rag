from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ...ingestion import IngestionPipeline, StageSpec
from ...ingestion.models import IngestResult
from ...ingestion.stages.chunking.chunker import ChunkerStage
from ...ingestion.stages.chunking.sectioner import SectionerStage
from ...ingestion.stages.embedding.embedding import EmbeddingStage, EncodingStrategy
from ...ingestion.stages.receive.dedup import DedupDecision, DedupStage
from ...ingestion.stages.receive.loader import LoaderStage
from ...ingestion.stages.storage.assets import AssetStore
from ...ingestion.stages.storage.fs import FsStore
from ...ingestion.stages.storage.fts5 import Fts5Store
from ...ingestion.stages.storage.sqlite import SqliteStore
from ...ingestion.stages.storage.upsert import UpsertResult, UpsertStage
from ...ingestion.stages.transform.asset_normalize import FsAssetNormalizer
from ...ingestion.stages.transform.transform_post import TransformPostStage
from ...ingestion.stages.transform.transform_pre import DefaultTransformPre, TransformPreStage
from ...libs.providers import register_builtin_providers
from ...libs.registry import ProviderRegistry
from ..response import ResponseIR
from ..strategy import StrategyLoader, load_settings


@dataclass
class IngestState:
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


PipelineBuilder = Callable[[str, Path], IngestionPipeline]


@dataclass
class IngestRunner:
    """User-facing ingestion entry for core (MCP tool will call this).

    E-5 scope: accept a local file path, run the offline ingestion pipeline,
    and return a ResponseIR (MCP will wrap + degrade by client level).
    """

    pipeline_builder: PipelineBuilder | None = None
    settings_path: str | Path = "config/settings.yaml"

    def run(
        self,
        file_path: str | Path,
        *,
        strategy_config_id: str,
        policy: str = "skip",
    ) -> ResponseIR:
        p = Path(file_path).expanduser().resolve()
        if not p.exists() or not p.is_file():
            return ResponseIR(
                trace_id="",
                content_md=f"ingest failed: file not found: {p}",
                sources=[],
                structured={"status": "error", "reason": "file_not_found", "file_path": str(p)},
            )

        pipeline = (
            self.pipeline_builder(strategy_config_id, Path(self.settings_path))
            if self.pipeline_builder is not None
            else _build_ingestion_pipeline(strategy_config_id, settings_path=Path(self.settings_path))
        )

        state = IngestState(input_path=p, policy=policy)
        result: IngestResult = pipeline.run(state, strategy_config_id=strategy_config_id)
        return _result_to_response(result)


def _build_ingestion_pipeline(strategy_config_id: str, *, settings_path: Path) -> IngestionPipeline:
    settings = load_settings(settings_path)
    strategy = StrategyLoader().load(strategy_config_id)

    registry = ProviderRegistry()
    register_builtin_providers(registry)

    # Stores (cross-stage dependencies)
    fs_store = FsStore(raw_dir=settings.paths.raw_dir, md_dir=settings.paths.md_dir)
    sqlite_store = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")
    fts5 = Fts5Store(db_path=settings.paths.sqlite_dir / "fts.sqlite")
    assets_dir = settings.paths.assets_dir
    assets_store = AssetStore(assets_dir=assets_dir)

    # Providers (config-driven)
    loader_provider_id, loader_params = strategy.resolve_provider("loader")
    sectioner_provider_id, sectioner_params = strategy.resolve_provider("sectioner")
    chunker_provider_id, chunker_params = strategy.resolve_provider("chunker")
    embedder_provider_id, embedder_params = strategy.resolve_provider("embedder")
    vector_provider_id, vector_params = strategy.resolve_provider("vector_index")

    # Text norm profile id should be consistent across chunk_id + retrieval caching.
    text_norm_profile_id = "default"
    try:
        _, retr_params = strategy.resolve_provider("retriever")
        tnp = retr_params.get("text_norm_profile_id")
        if isinstance(tnp, str) and tnp:
            text_norm_profile_id = tnp
    except Exception:
        pass

    # Loader dispatch: md uses configured provider; pdf always available as built-in.
    md_loader = registry.create("loader", loader_provider_id, **(loader_params or {}))
    pdf_loader = registry.create("loader", "loader.pdf")
    loader_stage = LoaderStage(loaders={"md": md_loader, "pdf": pdf_loader})

    sectioner_impl = registry.create("sectioner", sectioner_provider_id, **(sectioner_params or {}))
    chunker_impl = registry.create("chunker", chunker_provider_id, **(chunker_params or {}))

    embedder = registry.create("embedder", embedder_provider_id, **(embedder_params or {}))

    # Vector index: prefer persisted ChromaLite path unless overridden.
    vec_kwargs = dict(vector_params or {})
    if vector_provider_id == "vector.chroma_lite" and "db_path" not in vec_kwargs:
        vec_kwargs["db_path"] = str(settings.paths.chroma_dir / "chroma_lite.sqlite")
    vector_index = registry.create("vector_index", vector_provider_id, **vec_kwargs)

    # Stages
    dedup = DedupStage(fs_store=fs_store, sqlite_store=sqlite_store)
    normalizer = FsAssetNormalizer(asset_store=assets_store)
    transform_pre = TransformPreStage(transformer=DefaultTransformPre(profile_id="default"))
    sectioner = SectionerStage(sectioner=sectioner_impl)
    chunker = ChunkerStage(chunker=chunker_impl, text_norm_profile_id=text_norm_profile_id)
    transform_post = TransformPostStage()
    embedding = EmbeddingStage(
        embedder=embedder,
        embedder_id=embedder_provider_id,
        embedder_version=str(embedder_params.get("version", "0")) if isinstance(embedder_params, dict) else "0",
    )
    upsert = UpsertStage(
        fs=fs_store,
        sqlite=sqlite_store,
        vector_index=vector_index,
        fts5=fts5,
        assets_dir=assets_dir,
    )

    def st_dedup(state: IngestState, ctx) -> IngestState:
        dec = dedup.run(state.input_path, policy=state.policy)  # type: ignore[arg-type]
        state.dedup = dec
        state.skipped = dec.decision == "skip"
        return state

    def st_loader(state: IngestState, ctx) -> IngestState:
        if state.skipped:
            return state
        assert state.dedup is not None
        out = loader_stage.run(state.dedup.raw_path, doc_id=state.doc_id, version_id=state.version_id)
        state.md = out.md
        state.loader_assets = out.assets
        return state

    def st_asset_normalize(state: IngestState, ctx) -> IngestState:
        if state.skipped:
            return state
        assert state.dedup is not None and state.md is not None and state.loader_assets is not None
        state.normalized_assets = normalizer.normalize(
            state.loader_assets, raw_path=str(state.dedup.raw_path), md=state.md
        )
        return state

    def st_transform_pre(state: IngestState, ctx) -> IngestState:
        if state.skipped:
            return state
        assert state.md is not None
        state.md_norm = transform_pre.run(state.md, state.normalized_assets)
        return state

    def st_sectioner(state: IngestState, ctx) -> IngestState:
        if state.skipped:
            return state
        assert state.md_norm is not None
        sections, _ = sectioner.run(state.md_norm, doc_id=state.doc_id)
        state.sections = sections
        return state

    def st_chunker(state: IngestState, ctx) -> IngestState:
        if state.skipped:
            return state
        assert state.sections is not None
        chunks, _ = chunker.run(state.sections)
        for c in chunks:
            c.metadata["doc_id"] = state.doc_id
            c.metadata["version_id"] = state.version_id
        state.chunks = chunks
        return state

    def st_transform_post(state: IngestState, ctx) -> IngestState:
        if state.skipped:
            return state
        assert state.chunks is not None
        state.chunks = transform_post.run(state.chunks)
        return state

    def st_embedding(state: IngestState, ctx) -> IngestState:
        if state.skipped:
            return state
        assert state.chunks is not None
        # Default to hybrid to keep dense/sparse index parity for online query.
        state.encoded = embedding.run(state.chunks, EncodingStrategy(mode="hybrid"))
        return state

    def st_upsert(state: IngestState, ctx) -> IngestState:
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


def _result_to_response(result: IngestResult) -> ResponseIR:
    trace_id = result.trace_id
    if result.status != "ok" or not isinstance(result.output, IngestState):
        err = str(result.error) if result.error is not None else "unknown"
        r = ResponseIR(
            trace_id=trace_id,
            content_md=f"ingest failed: {err}",
            sources=[],
            structured={"status": "error", "error": err},
        )
        r.trace = result.trace
        return r

    st: IngestState = result.output
    dec = st.dedup
    assert dec is not None

    if st.skipped:
        md = "\n".join(
            [
                "Ingest skipped (dedup hit).",
                f"- doc_id: `{dec.doc_id}`",
                f"- version_id: `{dec.version_id}`",
                f"- file_sha256: `{dec.file_sha256}`",
                f"- decision: `{dec.decision}`",
            ]
        )
        r = ResponseIR(
            trace_id=trace_id,
            content_md=md,
            sources=[],
            structured={
                "status": "skipped",
                "decision": dec.decision,
                "doc_id": dec.doc_id,
                "version_id": dec.version_id,
                "file_sha256": dec.file_sha256,
            },
        )
        r.trace = result.trace
        return r

    up = st.upsert
    assert up is not None
    md = "\n".join(
        [
            "Ingest OK.",
            f"- doc_id: `{dec.doc_id}`",
            f"- version_id: `{dec.version_id}`",
            f"- md_path: `{up.md_path}`",
            f"- chunks_written: `{up.chunks_written}`",
            f"- assets_written: `{up.assets_written}`",
            f"- dense_written: `{up.dense_written}`",
            f"- sparse_written: `{up.sparse_written}`",
        ]
    )
    r = ResponseIR(
        trace_id=trace_id,
        content_md=md,
        sources=[],
        structured={
            "status": "ok",
            "decision": dec.decision,
            "doc_id": dec.doc_id,
            "version_id": dec.version_id,
            "file_sha256": dec.file_sha256,
            "md_path": str(up.md_path),
            "counts": {
                "chunks_written": up.chunks_written,
                "assets_written": up.assets_written,
                "dense_written": up.dense_written,
                "sparse_written": up.sparse_written,
            },
        },
    )
    r.trace = result.trace
    return r
