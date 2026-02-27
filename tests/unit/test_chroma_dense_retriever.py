from __future__ import annotations

from src.libs.providers.embedding.fake_embedder import FakeEmbedder
from src.libs.providers.vector_store.chroma_retriever import ChromaDenseRetriever
from src.libs.providers.vector_store.in_memory import InMemoryVectorIndex
from src.libs.interfaces.vector_store import VectorItem


def test_chroma_dense_retriever_topk() -> None:
    embedder = FakeEmbedder(dim=8)
    index = InMemoryVectorIndex()

    # Two chunks with different vectors
    v1 = embedder.embed_texts(["alpha"])[0]
    v2 = embedder.embed_texts(["beta"])[0]
    index.upsert([VectorItem(chunk_id="chk_a", vector=v1), VectorItem(chunk_id="chk_b", vector=v2)])

    retriever = ChromaDenseRetriever(embedder=embedder, vector_index=index)
    hits = retriever.retrieve("alpha", top_k=1)
    assert hits and hits[0].chunk_id == "chk_a"

