from __future__ import annotations

from dataclasses import dataclass

from ..strategy.loader import StrategyLoader
from ..strategy.models import StrategyConfig
from ...libs.factories import make_embedding, make_llm
from ...libs.providers import register_builtin_providers
from ...libs.registry import ProviderRegistry
from ...libs.interfaces.embedding import Embedder, SparseEncoder
from ...libs.interfaces.llm import LLM


@dataclass
class Runtime:
    strategy: StrategyConfig
    registry: ProviderRegistry
    embedder: Embedder
    llm: LLM
    sparse_encoder: SparseEncoder | None = None


def build_runtime_from_strategy(strategy_config_id: str) -> Runtime:
    loader = StrategyLoader()
    strategy = loader.load(strategy_config_id)

    registry = ProviderRegistry()
    register_builtin_providers(registry)

    cfg = strategy.to_factory_cfg()
    embedder, sparse_encoder = make_embedding(cfg, registry)
    llm = make_llm(cfg, registry)

    return Runtime(
        strategy=strategy,
        registry=registry,
        embedder=embedder,
        llm=llm,
        sparse_encoder=sparse_encoder,
    )
