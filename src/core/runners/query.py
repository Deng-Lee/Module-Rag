from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..query_engine import QueryParams, QueryPipeline, QueryRuntime
from ..response import ResponseIR
from ..strategy import StrategyLoader, load_settings
from ...ingestion.stages.storage.sqlite import SqliteStore
from ...libs.factories import make_embedding, make_llm
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
        ctx = TraceContext.new(trace_type="query", strategy_config_id=strategy_config_id)
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
    llm = make_llm(cfg, registry)

    vec_provider_id, vec_params = strategy.resolve_provider("vector_index")
    vec_kwargs = dict(vec_params or {})
    # Keep vector store location aligned to settings paths (important for local tests and MCP tools).
    if vec_provider_id == "vector.chroma_lite" and "db_path" not in vec_kwargs:
        vec_kwargs["db_path"] = str(settings.paths.chroma_dir / "chroma_lite.sqlite")
    vector_index = registry.create("vector_index", vec_provider_id, **vec_kwargs)

    # Dense retriever: injected with embedder + vector_index.
    try:
        retriever_provider_id, retriever_params = strategy.resolve_provider("retriever")
    except Exception:
        retriever_provider_id, retriever_params = "retriever.chroma_dense", {}
    retriever = registry.create(
        "retriever",
        retriever_provider_id,
        embedder=embedder,
        vector_index=vector_index,
        **retriever_params,
    )

    # Sparse retriever (optional).
    sparse_retriever = None
    try:
        sparse_provider_id, sparse_params = strategy.resolve_provider("sparse_retriever")
        sparse_retriever = registry.create(
            "sparse_retriever",
            sparse_provider_id,
            db_path=str(settings.paths.sqlite_dir / "fts.sqlite"),
            **(sparse_params or {}),
        )
    except Exception:
        sparse_retriever = None

    sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")

    # Fusion (optional; default to RRF if available).
    fusion = None
    try:
        fusion_provider_id, fusion_params = strategy.resolve_provider("fusion")
        fusion = registry.create("fusion", fusion_provider_id, **(fusion_params or {}))
    except Exception:
        try:
            fusion = registry.create("fusion", "fusion.rrf")
        except Exception:
            fusion = None

    # Reranker (optional).
    reranker = None
    try:
        reranker_provider_id, reranker_params = strategy.resolve_provider("reranker")
        if reranker_provider_id not in {"noop", "reranker.noop"}:
            reranker = registry.create("reranker", reranker_provider_id, **(reranker_params or {}))
        else:
            reranker = None
    except Exception:
        reranker = None

    return QueryRuntime(
        embedder=embedder,
        vector_index=vector_index,
        retriever=retriever,
        sparse_retriever=sparse_retriever,
        sqlite=sqlite,
        fusion=fusion,
        reranker=reranker,
        llm=llm,
    )
