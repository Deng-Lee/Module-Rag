from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

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


@pytest.mark.integration
def test_upsert_closed_loop_writes_fs_sqlite_chroma_and_fts5(
    tmp_path: Path, tmp_workdir: Path, mock_clock: float
) -> None:
    _ = tmp_workdir
    _ = mock_clock

    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    md_dir = data_dir / "md"
    assets_dir = data_dir / "assets"
    sqlite_dir = data_dir / "sqlite"
    chroma_dir = data_dir / "chroma"

    # fixture files
    img_path = tmp_path / "img.png"
    img_path.write_bytes(b"\x89PNG\r\n\x1a\nfake")

    md_path = tmp_path / "doc.md"
    md_text = (
        "# Install\n\n"
        "Use unicorn to validate sparse retrieval.\n\n"
        f"![logo]({img_path.as_posix()})\n\n"
        "## FAQ\n\n"
        "Chroma + FTS5.\n"
    )
    md_path.write_text(md_text, encoding="utf-8")

    fs_store = FsStore(raw_dir=raw_dir, md_dir=md_dir)
    sqlite_store = SqliteStore(db_path=sqlite_dir / "app.sqlite")

    dedup = DedupStage(fs_store=fs_store, sqlite_store=sqlite_store)
    dec = dedup.run(md_path, policy="skip")
    assert dec.decision == "continue"

    loader = LoaderStage(loaders={"md": MarkdownLoader()})
    loaded = loader.run(dec.raw_path, doc_id=dec.doc_id, version_id=dec.version_id)
    assert loaded.md

    normalized = FsAssetNormalizer(asset_store=AssetStore(assets_dir=assets_dir)).normalize(
        loaded.assets, raw_path=str(dec.raw_path), md=loaded.md
    )
    assert normalized.ref_to_asset_id

    md_norm = TransformPreStage(transformer=DefaultTransformPre(profile_id="default")).run(
        loaded.md, normalized
    )
    assert "asset://" in md_norm

    sections, _ = SectionerStage(sectioner=MarkdownHeadingsSectioner()).run(
        md_norm, doc_id=dec.doc_id
    )
    chunks, _ = ChunkerStage(
        chunker=RecursiveCharChunkerWithinSection(chunk_size=2000, chunk_overlap=0),
        text_norm_profile_id="default",
    ).run(sections)

    # Attach tracing/lineage fields early so downstream encoders can include them in metadata.
    for c in chunks:
        c.metadata["doc_id"] = dec.doc_id
        c.metadata["version_id"] = dec.version_id

    chunks = TransformPostStage().run(chunks)

    encoded = EmbeddingStage(embedder=FakeEmbedder(dim=8), embedder_id="embedder.fake", embedder_version="0").run(
        chunks, EncodingStrategy(mode="hybrid")
    )
    assert encoded.dense is not None
    assert encoded.sparse is not None

    vector_index = ChromaLiteVectorIndex(db_path=str(chroma_dir / "chroma_lite.sqlite"))
    fts5 = Fts5Store(db_path=sqlite_dir / "fts.sqlite")
    upsert = UpsertStage(
        fs=fs_store,
        sqlite=sqlite_store,
        vector_index=vector_index,
        fts5=fts5,
        assets_dir=assets_dir,
    )
    res = upsert.run(
        doc_id=dec.doc_id,
        version_id=dec.version_id,
        md_norm=md_norm,
        loader_assets=loaded.assets,
        normalized_assets=normalized,
        sections=sections,
        chunks=chunks,
        encoded=encoded,
    )

    assert res.md_path.exists()
    assert res.chunks_written == len(chunks)
    assert res.dense_written == len(encoded.dense.items)
    assert res.sparse_written == len(encoded.sparse.docs)

    # SQLite can reverse-lookup chunk rows and version status should be indexed.
    with sqlite3.connect(sqlite_store.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM doc_versions WHERE version_id=?",
            (dec.version_id,),
        ).fetchone()
        assert row is not None and row["status"] == "indexed"

        row2 = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()
        assert int(row2["c"]) == len(chunks)

        row3 = conn.execute("SELECT COUNT(*) AS c FROM assets").fetchone()
        assert int(row3["c"]) >= 1

    # Sparse immediately queryable.
    sparse_hits = fts5.query("unicorn", top_k=5)
    assert sparse_hits

    # Dense index persisted and count matches.
    assert vector_index.count() == len(encoded.dense.items)

