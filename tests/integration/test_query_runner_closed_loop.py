from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.core.query_engine.models import QueryRuntime
from src.core.runners import QueryRunner
from src.ingestion.stages.chunking.chunker import ChunkerStage
from src.ingestion.stages.chunking.sectioner import SectionerStage
from src.ingestion.stages.embedding.embedding import EmbeddingStage, EncodingStrategy
from src.ingestion.stages.receive.dedup import DedupStage
from src.ingestion.stages.receive.loader import LoaderStage
from src.ingestion.stages.storage.assets import AssetStore
from src.ingestion.stages.storage.fs import FsStore
from src.ingestion.stages.storage.fts5 import Fts5Store
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.ingestion.stages.storage.upsert import UpsertStage
from src.ingestion.stages.transform.asset_normalize import FsAssetNormalizer
from src.ingestion.stages.transform.transform_post import TransformPostStage
from src.ingestion.stages.transform.transform_pre import DefaultTransformPre, TransformPreStage
from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.loader.markdown_loader import MarkdownLoader
from src.libs.providers.splitter.markdown_headings import MarkdownHeadingsSectioner
from src.libs.providers.splitter.recursive_chunker import RecursiveCharChunkerWithinSection
from src.libs.providers.vector_store.chroma_lite import ChromaLiteVectorIndex
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever
from src.libs.providers.vector_store.fts5_retriever import Fts5Retriever
from src.libs.providers.vector_store.rrf_fusion import RrfFusion


@pytest.mark.integration
def test_query_runner_on_ingested_db_returns_sources(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    md_dir = data_dir / "md"
    assets_dir = data_dir / "assets"
    sqlite_dir = data_dir / "sqlite"
    chroma_dir = data_dir / "chroma"

    # Minimal markdown (no image dependencies) to keep the fixture stable.
    md_path = tmp_path / "doc.md"
    md_path.write_text("# Title\n\nhello world from chunk\n", encoding="utf-8")

    fs_store = FsStore(raw_dir=raw_dir, md_dir=md_dir)
    sqlite_store = SqliteStore(db_path=sqlite_dir / "app.sqlite")
    fts5 = Fts5Store(db_path=sqlite_dir / "fts.sqlite")
    vector_index = ChromaLiteVectorIndex(db_path=str(chroma_dir / "chroma_lite.sqlite"))

    dec = DedupStage(fs_store=fs_store, sqlite_store=sqlite_store).run(md_path, policy="skip")
    assert dec.decision == "continue"

    loaded = LoaderStage(loaders={"md": MarkdownLoader()}).run(dec.raw_path, doc_id=dec.doc_id, version_id=dec.version_id)
    normalized = FsAssetNormalizer(asset_store=AssetStore(assets_dir=assets_dir)).normalize(
        loaded.assets, raw_path=str(dec.raw_path), md=loaded.md
    )
    md_norm = TransformPreStage(transformer=DefaultTransformPre(profile_id="default")).run(loaded.md, normalized)

    sections, _ = SectionerStage(sectioner=MarkdownHeadingsSectioner()).run(md_norm, doc_id=dec.doc_id)
    chunks, _ = ChunkerStage(
        chunker=RecursiveCharChunkerWithinSection(chunk_size=2000, chunk_overlap=0),
        text_norm_profile_id="default",
    ).run(sections)
    for c in chunks:
        c.metadata["doc_id"] = dec.doc_id
        c.metadata["version_id"] = dec.version_id
    chunks = TransformPostStage().run(chunks)

    embedder = FakeEmbedder(dim=8)
    encoded = EmbeddingStage(embedder=embedder, embedder_id="embedder.fake", embedder_version="0").run(
        chunks, EncodingStrategy(mode="dense")
    )
    assert encoded.dense is not None

    UpsertStage(
        fs=fs_store,
        sqlite=sqlite_store,
        vector_index=vector_index,
        fts5=fts5,
        assets_dir=assets_dir,
    ).run(
        doc_id=dec.doc_id,
        version_id=dec.version_id,
        md_norm=md_norm,
        loader_assets=loaded.assets,
        normalized_assets=normalized,
        sections=sections,
        chunks=chunks,
        encoded=encoded,
    )

    # Pick an existing chunk_text as query so FakeEmbedder guarantees a best-match (cosine=1.0).
    with sqlite3.connect(sqlite_store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT chunk_id, chunk_text FROM chunks LIMIT 1").fetchone()
    assert row is not None
    chunk_id = str(row["chunk_id"])
    chunk_text = str(row["chunk_text"])

    def build_rt(_: str) -> QueryRuntime:
        vector_idx = ChromaLiteVectorIndex(db_path=str(chroma_dir / "chroma_lite.sqlite"))
        embed = embedder
        return QueryRuntime(
            embedder=embed,
            vector_index=vector_idx,
            retriever=ChromaDenseRetriever(embedder=embed, vector_index=vector_idx),
            sparse_retriever=Fts5Retriever(db_path=str(sqlite_dir / "fts.sqlite")),
            sqlite=SqliteStore(db_path=sqlite_dir / "app.sqlite"),
            fusion=RrfFusion(k=60),
            reranker=None,
        )

    resp = QueryRunner(runtime_builder=build_rt).run(chunk_text, strategy_config_id="local.default", top_k=3)
    assert resp.sources
    assert resp.sources[0].chunk_id == chunk_id
    assert resp.trace is not None
    assert [s.name for s in resp.trace.spans] == [
        "stage.query_norm",
        "stage.retrieve_dense",
        "stage.retrieve_sparse",
        "stage.fusion",
        "stage.rerank",
        "stage.context_build",
        "stage.format_response",
    ]
