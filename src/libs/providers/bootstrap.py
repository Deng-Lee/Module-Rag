from __future__ import annotations

from ..registry import ProviderRegistry
from .embedding.fake_embedder import FakeEmbedder
from .loader.markdown_loader import MarkdownLoader
from .loader.pdf_loader import PdfLoader
from .llm.fake_llm import FakeLLM
from .reranker.noop import NoopReranker
from .splitter.markdown_headings import MarkdownHeadingsSectioner
from .splitter.recursive_chunker import RecursiveCharChunkerWithinSection
from .splitter.simple_chunker import SimpleCharChunkerWithinSection
from .vector_store.in_memory import InMemoryVectorIndex
from .vector_store.chroma_lite import ChromaLiteVectorIndex
from .vector_store.chroma_retriever import ChromaDenseRetriever
from .vector_store.fts5_retriever import Fts5Retriever
from .vector_store.rrf_fusion import RrfFusion


def register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register default providers for local/dev runs."""

    registry.register("embedder", "embedder.fake", FakeEmbedder)
    registry.register("embedder", "embedder.fake_alt", FakeEmbedder)
    registry.register("loader", "loader.markdown", MarkdownLoader)
    registry.register("loader", "loader.pdf", PdfLoader)
    registry.register("sectioner", "sectioner.markdown_headings", MarkdownHeadingsSectioner)
    registry.register("chunker", "chunker.rcts_within_section", RecursiveCharChunkerWithinSection)
    registry.register("chunker", "chunker.simple_char_within_section", SimpleCharChunkerWithinSection)
    registry.register("llm", "llm.fake", FakeLLM)
    registry.register("vector_index", "vector.in_memory", InMemoryVectorIndex)
    registry.register("vector_index", "vector.chroma_lite", ChromaLiteVectorIndex)
    registry.register("retriever", "retriever.chroma_dense", ChromaDenseRetriever)
    registry.register("sparse_retriever", "sparse_retriever.fts5", Fts5Retriever)
    registry.register("fusion", "fusion.rrf", RrfFusion)
    registry.register("reranker", "reranker.noop", NoopReranker)
