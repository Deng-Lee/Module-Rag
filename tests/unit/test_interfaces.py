from __future__ import annotations

from src.libs.interfaces.embedding import Embedder, SparseEncoder
from src.libs.interfaces.evaluator import EvalReport, Evaluator
from src.libs.interfaces.llm import LLM, LLMResult
from src.libs.interfaces.loader import AssetNormalizer, AssetRef, BaseLoader, LoaderOutput, ParseSummary, NormalizedAssets
from src.libs.interfaces.reranker import Reranker
from src.libs.interfaces.splitter import ChunkIR, Chunker, SectionIR, Sectioner
from src.libs.interfaces.vector_store import Candidate, Fusion, RankedCandidate, Retriever, SparseIndex, VectorIndex, VectorItem


class FakeLoader:
    def load(self, input_path: str, *, doc_id: str | None = None, version_id: str | None = None) -> LoaderOutput:
        return LoaderOutput(md="x", assets=[], parse_summary=ParseSummary())


class FakeAssetNormalizer:
    def normalize(self, assets: list[AssetRef], *, raw_path: str, md: str) -> NormalizedAssets:
        return NormalizedAssets(ref_to_asset_id={})


class FakeSectioner:
    def section(self, md_norm: str) -> list[SectionIR]:
        return [SectionIR(section_id="s1", section_path="/", text=md_norm)]


class FakeChunker:
    def chunk(self, sections: list[SectionIR]) -> list[ChunkIR]:
        return [ChunkIR(chunk_id="c1", section_path=sections[0].section_path, text=sections[0].text)]


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] for t in texts]


class FakeSparseEncoder:
    def encode(self, texts: list[str]) -> list[dict]:
        return [{"text": t} for t in texts]


class FakeVectorIndex:
    def upsert(self, items: list[VectorItem]) -> None:
        return None

    def query(self, vector: list[float], top_k: int) -> list[tuple[str, float]]:
        return []


class FakeSparseIndex:
    def upsert(self, items: list[dict]) -> None:
        return None

    def query(self, query_expr: str, top_k: int) -> list[tuple[str, float]]:
        return []


class FakeRetriever:
    def retrieve(self, query: str, top_k: int) -> list[Candidate]:
        return [Candidate(chunk_id="c1", score=1.0, source="dense")]


class FakeFusion:
    def fuse(self, candidates_by_source: dict[str, list[Candidate]]) -> list[RankedCandidate]:
        return [RankedCandidate(chunk_id="c1", score=1.0, rank=1, source="fusion")]


class FakeReranker:
    def rerank(self, query: str, candidates: list[RankedCandidate]) -> list[RankedCandidate]:
        return candidates


class FakeLLM:
    def generate(self, mode: str, messages: list[dict], **kwargs) -> LLMResult:
        return LLMResult(text="ok")


class FakeEvaluator:
    def run(self, dataset_id: str, strategy_config_id: str, mode: str = "offline") -> EvalReport:
        return EvalReport(run_id="r1", metrics={"mrr": 1.0})


def test_interfaces_min_contracts() -> None:
    loader: BaseLoader = FakeLoader()
    normalizer: AssetNormalizer = FakeAssetNormalizer()
    sectioner: Sectioner = FakeSectioner()
    chunker: Chunker = FakeChunker()
    embedder: Embedder = FakeEmbedder()
    sparse: SparseEncoder = FakeSparseEncoder()
    vindex: VectorIndex = FakeVectorIndex()
    sindex: SparseIndex = FakeSparseIndex()
    retriever: Retriever = FakeRetriever()
    fusion: Fusion = FakeFusion()
    reranker: Reranker = FakeReranker()
    llm: LLM = FakeLLM()
    evaluator: Evaluator = FakeEvaluator()

    out = loader.load("x.md")
    assert out.md == "x"
    assert isinstance(normalizer.normalize(out.assets, raw_path="x", md=out.md), NormalizedAssets)

    sections = sectioner.section(out.md)
    chunks = chunker.chunk(sections)
    vectors = embedder.embed_texts([c.text for c in chunks])
    sparse_docs = sparse.encode([c.text for c in chunks])
    assert len(vectors) == len(chunks)
    assert len(sparse_docs) == len(chunks)

    vindex.upsert([VectorItem(chunk_id="c1", vector=[0.1])])
    sindex.upsert(sparse_docs)
    candidates = retriever.retrieve("q", 1)
    ranked = fusion.fuse({"dense": candidates})
    reranked = reranker.rerank("q", ranked)
    assert len(reranked) >= 1

    res = llm.generate("answer", [{"role": "user", "content": "hi"}])
    assert res.text == "ok"

    report = evaluator.run("ds", "scfg")
    assert report.metrics["mrr"] == 1.0
