from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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
    sparse_provider_id: str | None = None
    sparse_params: dict | None = None
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
    fusion_provider_id: str | None = None
    fusion_params: dict | None = None
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
    reranker_provider_id: str | None = None
    reranker_params: dict | None = None
    try:
        reranker_provider_id, reranker_params = strategy.resolve_provider("reranker")
        if reranker_provider_id not in {"noop", "reranker.noop"}:
            reranker = registry.create("reranker", reranker_provider_id, **(reranker_params or {}))
        else:
            reranker = None
    except Exception:
        reranker = None

    _attach_providers_snapshot(
        strategy=strategy,
        vec_provider_id=vec_provider_id,
        vec_params=vec_kwargs,
        retriever_provider_id=retriever_provider_id,
        retriever_params=retriever_params,
        sparse_provider_id=sparse_provider_id,
        sparse_params=sparse_params,
        fusion_provider_id=fusion_provider_id,
        fusion_params=fusion_params,
        reranker_provider_id=reranker_provider_id,
        reranker_params=reranker_params,
    )

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


def _attach_providers_snapshot(
    *,
    strategy,
    vec_provider_id: str,
    vec_params: dict,
    retriever_provider_id: str,
    retriever_params: dict,
    sparse_provider_id: str | None,
    sparse_params: dict | None,
    fusion_provider_id: str | None,
    fusion_params: dict | None,
    reranker_provider_id: str | None,
    reranker_params: dict | None,
) -> None:
    ctx = TraceContext.current()
    if ctx is None:
        return

    def _meta(provider_id: str, params: dict | None) -> dict[str, Any]:
        params = params or {}
        profile_id = params.get("profile_id") or params.get("text_norm_profile_id")
        version = params.get("version") or params.get("model_version")
        meta = {"provider_id": provider_id}
        if profile_id:
            meta["profile_id"] = str(profile_id)
        if version:
            meta["version"] = str(version)
        return meta

    snapshot: dict[str, dict[str, Any]] = {}

    embedder_provider_id, embedder_params = strategy.resolve_provider("embedder")
    snapshot["embedder"] = _meta(embedder_provider_id, embedder_params)
    snapshot["vector_index"] = _meta(vec_provider_id, vec_params)
    snapshot["retriever"] = _meta(retriever_provider_id, retriever_params)

    try:
        llm_provider_id, llm_params = strategy.resolve_provider("llm")
        snapshot["llm"] = _meta(llm_provider_id, llm_params)
    except Exception:
        pass

    if sparse_provider_id:
        snapshot["sparse_retriever"] = _meta(sparse_provider_id, sparse_params)
    if fusion_provider_id:
        snapshot["fusion"] = _meta(fusion_provider_id, fusion_params)
    if reranker_provider_id:
        snapshot["reranker"] = _meta(reranker_provider_id, reranker_params)

    ctx.providers_snapshot = snapshot
