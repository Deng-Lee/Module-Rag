from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..query_engine import QueryParams, QueryPipeline, QueryRuntime
from ..response import ResponseIR
from ..strategy import StrategyLoader, load_settings
from ...ingestion.stages.storage.sqlite import SqliteStore
from ...libs.factories import make_embedding
from ...libs.providers import register_builtin_providers
from ...libs.registry import ProviderRegistry
from ...observability.trace.context import TraceContext


RuntimeBuilder = Callable[[str], QueryRuntime]


@dataclass
class QueryRunner:
    """User-facing query entry for core (MCP tool will call this).

    D-1 scope: no LLM generation; returns an extractive markdown response.
    """

    runtime_builder: RuntimeBuilder | None = None
    settings_path: str | Path = "config/settings.yaml"

    def run(
        self,
        query: str,
        *,
        strategy_config_id: str,
        top_k: int = 5,
        filters: dict | None = None,
    ) -> ResponseIR:
        ctx = TraceContext.new()
        with TraceContext.activate(ctx):
            runtime = (
                self.runtime_builder(strategy_config_id)
                if self.runtime_builder is not None
                else _build_query_runtime(strategy_config_id, settings_path=self.settings_path)
            )
            params = QueryParams(top_k=top_k, filters=filters)
            resp = QueryPipeline().run(query, runtime=runtime, params=params)
            resp.trace = ctx.finish()
            return resp


def _build_query_runtime(strategy_config_id: str, *, settings_path: str | Path) -> QueryRuntime:
    settings = load_settings(settings_path)
    strategy = StrategyLoader().load(strategy_config_id)

    registry = ProviderRegistry()
    register_builtin_providers(registry)

    cfg = strategy.to_factory_cfg()
    embedder, _ = make_embedding(cfg, registry)

    vec_provider_id, vec_params = strategy.resolve_provider("vector_index")
    vector_index = registry.create("vector_index", vec_provider_id, vec_params)

    sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")

    return QueryRuntime(embedder=embedder, vector_index=vector_index, sqlite=sqlite)

