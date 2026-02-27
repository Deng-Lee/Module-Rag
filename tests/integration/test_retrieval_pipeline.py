from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pytest

from src.core.query_engine import QueryParams, QueryPipeline, QueryRuntime
from src.ingestion.stages.chunking.chunker import ChunkerStage
from src.ingestion.stages.chunking.sectioner import SectionerStage
from src.ingestion.stages.embedding.embedding import EmbeddingStage, EncodingStrategy
from src.ingestion.stages.storage.assets import AssetStore
from src.ingestion.stages.storage.fs import FsStore
from src.ingestion.stages.storage.fts5 import Fts5Store
from src.ingestion.stages.storage.sqlite import SqliteStore
from src.ingestion.stages.storage.upsert import UpsertStage
from src.ingestion.stages.transform.asset_normalize import FsAssetNormalizer
from src.ingestion.stages.transform.transform_post import TransformPostStage
from src.ingestion.stages.transform.transform_pre import DefaultTransformPre, TransformPreStage
from src.libs.interfaces.vector_store import RankedCandidate
from src.libs.providers.embedding.bow_embedder import BowHashEmbedder
from src.libs.providers.loader.markdown_loader import MarkdownLoader
from src.libs.providers.splitter.markdown_headings import MarkdownHeadingsSectioner
from src.libs.providers.splitter.recursive_chunker import RecursiveCharChunkerWithinSection
from src.libs.providers.vector_store.chroma_lite import ChromaLiteVectorIndex
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever
from src.libs.providers.vector_store.fts5_retriever import Fts5Retriever
from src.libs.providers.vector_store.rrf_fusion import RrfFusion


@dataclass(frozen=True)
class _QueryCase:
    qid: str
    query: str
    k: int
    expected_terms: list[str]


def _load_dataset(path: Path) -> tuple[list[dict[str, Any]], list[_QueryCase]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    docs = list(raw["docs"])
    qs: list[_QueryCase] = []
    for q in raw["queries"]:
        qs.append(
            _QueryCase(
                qid=str(q["id"]),
                query=str(q["query"]),
                k=int(q.get("k", 5)),
                expected_terms=[str(t) for t in q.get("expected_terms", [])],
            )
        )
    return docs, qs


def _ingest_docs(
    *,
    tmp_path: Path,
    docs: list[dict[str, Any]],
    sqlite: SqliteStore,
    fts5: Fts5Store,
    vector_index: ChromaLiteVectorIndex,
    assets_dir: Path,
    raw_dir: Path,
    md_dir: Path,
) -> None:
    fs = FsStore(raw_dir=raw_dir, md_dir=md_dir)
    loader = MarkdownLoader()
    normalizer = FsAssetNormalizer(asset_store=AssetStore(assets_dir=assets_dir))
    transform_pre = TransformPreStage(transformer=DefaultTransformPre(profile_id="default"))
    sectioner = SectionerStage(sectioner=MarkdownHeadingsSectioner())
    chunker = ChunkerStage(
        chunker=RecursiveCharChunkerWithinSection(chunk_size=2000, chunk_overlap=0),
        text_norm_profile_id="default",
    )
    transform_post = TransformPostStage()

    embedder = BowHashEmbedder(dim=64)
    embedding = EmbeddingStage(embedder=embedder, embedder_id="embedder.bow", embedder_version="0")

    upsert = UpsertStage(
        fs=fs,
        sqlite=sqlite,
        vector_index=vector_index,
        fts5=fts5,
        assets_dir=assets_dir,
    )

    # Deterministic ids for regression: doc/version derived from doc name.
    for d in docs:
        name = str(d["name"])
        md_text = str(d["md"])
        path = tmp_path / f"{name}.md"
        path.write_text(md_text, encoding="utf-8")

        doc_id = f"doc_{name}"
        ver_id = f"ver_{name}"
        sha = f"sha_{name}"
        sqlite.upsert_doc_version_minimal(doc_id, ver_id, file_sha256=sha, status="pending")

        loaded = loader.load(str(path), doc_id=doc_id, version_id=ver_id)
        normalized = normalizer.normalize(loaded.assets, raw_path=str(path), md=loaded.md)
        md_norm = transform_pre.run(loaded.md, normalized)
        sections, _ = sectioner.run(md_norm, doc_id=doc_id)
        chunks, _ = chunker.run(sections)
        for c in chunks:
            c.metadata["doc_id"] = doc_id
            c.metadata["version_id"] = ver_id
        chunks = transform_post.run(chunks)
        encoded = embedding.run(chunks, EncodingStrategy(mode="hybrid"))

        upsert.run(
            doc_id=doc_id,
            version_id=ver_id,
            md_norm=md_norm,
            loader_assets=loaded.assets,
            normalized_assets=normalized,
            sections=sections,
            chunks=chunks,
            encoded=encoded,
        )


class _NoopRetriever:
    def retrieve(self, query: str, top_k: int) -> list:
        _ = query
        _ = top_k
        return []


def _run_query_cases(
    *,
    runtime: QueryRuntime,
    cases: Iterable[_QueryCase],
) -> dict[str, list[RankedCandidate]]:
    pipeline = QueryPipeline()
    out: dict[str, list[RankedCandidate]] = {}
    for c in cases:
        resp = pipeline.run(c.query, runtime=runtime, params=QueryParams(top_k=c.k))
        # Recompute ranked list from ResponseIR.sources (rank/order preserved).
        ranked: list[RankedCandidate] = []
        for s in resp.sources:
            ranked.append(
                RankedCandidate(
                    chunk_id=s.chunk_id,
                    score=float(s.score),
                    rank=int(s.rank or 0),
                    source=s.source,
                )
            )
        out[c.qid] = ranked
    return out


def _is_relevant(text: str, expected_terms: list[str]) -> bool:
    t = (text or "").lower()
    for term in expected_terms:
        if term.lower() in t:
            return True
    return False


def _hit_rate_at_k(rows_by_qid: dict[str, list[str]], cases: list[_QueryCase], k: int) -> float:
    hits = 0
    for c in cases:
        got = rows_by_qid.get(c.qid, [])[:k]
        if any(_is_relevant(txt, c.expected_terms) for txt in got):
            hits += 1
    return hits / max(1, len(cases))


def _mrr(rows_by_qid: dict[str, list[str]], cases: list[_QueryCase], k: int) -> float:
    acc = 0.0
    for c in cases:
        got = rows_by_qid.get(c.qid, [])[:k]
        rr = 0.0
        for i, txt in enumerate(got, start=1):
            if _is_relevant(txt, c.expected_terms):
                rr = 1.0 / i
                break
        acc += rr
    return acc / max(1, len(cases))


def _ndcg_at_k(rows_by_qid: dict[str, list[str]], cases: list[_QueryCase], k: int) -> float:
    def dcg(rels: list[int]) -> float:
        s = 0.0
        for i, rel in enumerate(rels[:k], start=1):
            if rel:
                s += 1.0 / math.log2(i + 1)
        return s

    acc = 0.0
    for c in cases:
        got = rows_by_qid.get(c.qid, [])[:k]
        rels = [1 if _is_relevant(txt, c.expected_terms) else 0 for txt in got]
        dcg_val = dcg(rels)
        idcg_val = dcg(sorted(rels, reverse=True))
        acc += (dcg_val / idcg_val) if idcg_val > 0 else 0.0
    return acc / max(1, len(cases))


@pytest.mark.integration
def test_retrieval_regression_metrics_across_strategies(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    ds_path = Path(__file__).resolve().parents[1] / "datasets" / "retrieval_small.yaml"
    docs, cases = _load_dataset(ds_path)

    data_dir = tmp_path / "data"
    sqlite_dir = data_dir / "sqlite"
    chroma_dir = data_dir / "chroma"
    assets_dir = data_dir / "assets"
    raw_dir = data_dir / "raw"
    md_dir = data_dir / "md"

    sqlite = SqliteStore(db_path=sqlite_dir / "app.sqlite")
    fts5 = Fts5Store(db_path=sqlite_dir / "fts.sqlite")
    vector_index = ChromaLiteVectorIndex(db_path=str(chroma_dir / "chroma_lite.sqlite"))

    _ingest_docs(
        tmp_path=tmp_path,
        docs=docs,
        sqlite=sqlite,
        fts5=fts5,
        vector_index=vector_index,
        assets_dir=assets_dir,
        raw_dir=raw_dir,
        md_dir=md_dir,
    )

    embedder = BowHashEmbedder(dim=64)
    dense_retriever = ChromaDenseRetriever(embedder=embedder, vector_index=vector_index)
    sparse_retriever = Fts5Retriever(db_path=str(sqlite_dir / "fts.sqlite"))

    def rows_for(runtime: QueryRuntime, k: int) -> dict[str, list[str]]:
        ranked_by_qid = _run_query_cases(runtime=runtime, cases=cases)
        out: dict[str, list[str]] = {}
        for c in cases:
            ids = [r.chunk_id for r in ranked_by_qid.get(c.qid, [])[:k]]
            texts = [r.chunk_text for r in sqlite.fetch_chunks(ids)]
            out[c.qid] = texts
        return out

    strategies: dict[str, QueryRuntime] = {
        "dense_only": QueryRuntime(embedder=embedder, vector_index=vector_index, retriever=dense_retriever, sqlite=sqlite),
        "sparse_only": QueryRuntime(embedder=embedder, vector_index=vector_index, retriever=_NoopRetriever(), sparse_retriever=sparse_retriever, sqlite=sqlite),  # type: ignore[arg-type]
        "hybrid_passthrough": QueryRuntime(embedder=embedder, vector_index=vector_index, retriever=dense_retriever, sparse_retriever=sparse_retriever, sqlite=sqlite),
        "hybrid_rrf": QueryRuntime(embedder=embedder, vector_index=vector_index, retriever=dense_retriever, sparse_retriever=sparse_retriever, fusion=RrfFusion(k=60), sqlite=sqlite),
    }

    metrics: dict[str, dict[str, float]] = {}
    for name, rt in strategies.items():
        rows = rows_for(rt, k=5)
        metrics[name] = {
            "hit@5": _hit_rate_at_k(rows, cases, k=5),
            "mrr@5": _mrr(rows, cases, k=5),
            "ndcg@5": _ndcg_at_k(rows, cases, k=5),
        }

    # Basic sanity: metrics are well-formed.
    for name, m in metrics.items():
        assert 0.0 <= m["hit@5"] <= 1.0
        assert 0.0 <= m["mrr@5"] <= 1.0
        assert 0.0 <= m["ndcg@5"] <= 1.0

    # Regression-friendly guard: hybrid_rrf should not be worse than hybrid_passthrough on this tiny dataset.
    assert metrics["hybrid_rrf"]["hit@5"] >= metrics["hybrid_passthrough"]["hit@5"]

