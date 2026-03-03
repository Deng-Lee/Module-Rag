from __future__ import annotations

from ..registry import ProviderRegistry
from .embedding.fake_embedder import FakeEmbedder
from .embedding.bow_embedder import BowHashEmbedder
from .embedding.openai_compatible import OpenAICompatibleEmbedder
from .embedding.azure_openai import AzureOpenAIEmbedder
from .loader.markdown_loader import MarkdownLoader
from .loader.pdf_loader import PdfLoader
from .llm.fake_llm import FakeLLM
from .llm.openai_compatible import OpenAICompatibleLLM
from .llm.azure_openai import AzureOpenAILLM
from .reranker.noop import NoopReranker
from .reranker.openai_compatible_llm import OpenAICompatibleLLMReranker
from .enricher.noop import NoopEnricher
from .enricher.openai_compatible_vision import OpenAICompatibleVisionEnricher
from .splitter.markdown_headings import MarkdownHeadingsSectioner
from .splitter.recursive_chunker import RecursiveCharChunkerWithinSection
from .splitter.simple_chunker import SimpleCharChunkerWithinSection
from .evaluator.fake_judge import FakeJudge
from .evaluator.judge_openai_compatible import OpenAICompatibleJudge
from .evaluator.judge_azure_openai import AzureOpenAIJudge
from .evaluator.composite import CompositeEvaluatorProvider
from .evaluator.ragas_adapter import RagasAdapter
from .evaluator.deepeval_adapter import DeepEvalAdapter
from .vector_store.in_memory import InMemoryVectorIndex
from .vector_store.chroma import ChromaVectorIndex
from .vector_store.chroma_lite import ChromaLiteVectorIndex
from .vector_store.chroma_retriever import ChromaDenseRetriever
from .vector_store.fts5_retriever import Fts5Retriever
from .vector_store.rrf_fusion import RrfFusion


def register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register default providers for local/dev runs."""

    registry.register("embedder", "fake", FakeEmbedder)
    registry.register("embedder", "fake_alt", FakeEmbedder)
    registry.register("embedder", "bow", BowHashEmbedder)
    registry.register("embedder", "openai_compatible", OpenAICompatibleEmbedder)
    registry.register("embedder", "openai", OpenAICompatibleEmbedder)
    registry.register("embedder", "deepseek", OpenAICompatibleEmbedder)
    registry.register("embedder", "qwen", OpenAICompatibleEmbedder)
    registry.register("embedder", "azure_openai", AzureOpenAIEmbedder)
    registry.register("loader", "loader.markdown", MarkdownLoader)
    registry.register("loader", "loader.pdf", PdfLoader)
    registry.register("sectioner", "sectioner.markdown_headings", MarkdownHeadingsSectioner)
    registry.register("chunker", "chunker.rcts_within_section", RecursiveCharChunkerWithinSection)
    registry.register("chunker", "chunker.simple_char_within_section", SimpleCharChunkerWithinSection)
    registry.register("llm", "fake", FakeLLM)
    registry.register("llm", "openai_compatible", OpenAICompatibleLLM)
    registry.register("llm", "openai", OpenAICompatibleLLM)
    registry.register("llm", "deepseek", OpenAICompatibleLLM)
    registry.register("llm", "qwen", OpenAICompatibleLLM)
    registry.register("llm", "azure_openai", AzureOpenAILLM)
    registry.register("vector_index", "vector.in_memory", InMemoryVectorIndex)
    registry.register("vector_index", "vector.chroma", ChromaVectorIndex)
    registry.register("vector_index", "vector.chroma_lite", ChromaLiteVectorIndex)
    registry.register("retriever", "retriever.chroma_dense", ChromaDenseRetriever)
    registry.register("sparse_retriever", "sparse_retriever.fts5", Fts5Retriever)
    registry.register("fusion", "fusion.rrf", RrfFusion)
    registry.register("reranker", "noop", NoopReranker)
    # Back-compat alias (do not use in new configs).
    registry.register("reranker", "reranker.noop", NoopReranker)
    registry.register("reranker", "openai_compatible_llm", OpenAICompatibleLLMReranker)
    registry.register("judge", "fake", FakeJudge)
    registry.register("judge", "openai_compatible", OpenAICompatibleJudge)
    registry.register("judge", "openai", OpenAICompatibleJudge)
    registry.register("judge", "deepseek", OpenAICompatibleJudge)
    registry.register("judge", "qwen", OpenAICompatibleJudge)
    registry.register("judge", "azure_openai", AzureOpenAIJudge)
    registry.register("evaluator", "composite", CompositeEvaluatorProvider)
    registry.register("evaluator", "ragas", RagasAdapter)
    registry.register("evaluator", "deepeval", DeepEvalAdapter)

    # Ingestion enrichers (OCR/Caption etc.). Defaults to noop.
    registry.register("enricher", "noop", NoopEnricher)
    registry.register("enricher", "openai_compatible_vision", OpenAICompatibleVisionEnricher)
