from __future__ import annotations

from ..registry import ProviderRegistry
from .embedding.fake_embedder import FakeEmbedder
from .llm.fake_llm import FakeLLM
from .reranker.noop import NoopReranker
from .vector_store.in_memory import InMemoryVectorIndex


def register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register default providers for local/dev runs."""

    registry.register("embedder", "embedder.fake", FakeEmbedder)
    registry.register("embedder", "embedder.fake_alt", FakeEmbedder)
    registry.register("llm", "llm.fake", FakeLLM)
    registry.register("vector_index", "vector.in_memory", InMemoryVectorIndex)
    registry.register("reranker", "reranker.noop", NoopReranker)
