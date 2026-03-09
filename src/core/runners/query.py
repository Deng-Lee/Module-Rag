from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ...ingestion.stages.storage.sqlite import SqliteStore
from ...libs.factories import make_embedding, make_llm
from ...libs.providers import register_builtin_providers
from ...libs.registry import ProviderRegistry
from ...observability.trace.context import TraceContext
from ..query_engine import QueryParams, QueryPipeline, QueryRuntime
from ..response import ResponseIR
from ..strategy import Settings, StrategyLoader, load_settings, merge_provider_overrides

RuntimeBuilder = Callable[[str], QueryRuntime]


@dataclass
class _InitErrorReranker:
    provider_id: str
    err_message: str

    def rerank(self, query: str, candidates: list) -> list:
        _ = query, candidates
        raise RuntimeError(f"reranker_init_failed:{self.provider_id}:{self.err_message}")


@dataclass
class QueryRunner:
    """User-facing query entry for core (MCP tool will call this).

    D-1 scope: no LLM generation; returns an extractive markdown response.
    """

    runtime_builder: RuntimeBuilder | None = None
    settings_path: str | Path = "config/settings.yaml"
    settings: Settings | None = None

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
            if self.runtime_builder is not None:
                runtime = self.runtime_builder(strategy_config_id)
            elif self.settings is not None:
                runtime = _build_query_runtime_from_settings(
                    strategy_config_id,
                    settings=self.settings,
                )
            else:
                runtime = _build_query_runtime(strategy_config_id, settings_path=self.settings_path)
            params = QueryParams(top_k=top_k, filters=filters)
            resp = QueryPipeline().run(query, runtime=runtime, params=params)
            resp.trace = ctx.finish()
            return resp


def _build_query_runtime(strategy_config_id: str, *, settings_path: str | Path) -> QueryRuntime:
    settings = load_settings(settings_path)
    return _build_query_runtime_from_settings(strategy_config_id, settings=settings)


def _build_query_runtime_from_settings(
    strategy_config_id: str,
    *,
    settings: Settings,
) -> QueryRuntime:
    strategy = StrategyLoader().load(strategy_config_id)

    registry = ProviderRegistry()
    register_builtin_providers(registry)

    merged_providers = merge_provider_overrides(
        strategy.providers,
        settings.raw.get("providers"),
        settings.raw.get("model_endpoints"),
    )
    strategy.providers = merged_providers
    cfg = strategy.to_factory_cfg()
    embedder, _ = make_embedding(cfg, registry)
    llm = make_llm(cfg, registry)

    vec_provider_id, vec_params = strategy.resolve_provider("vector_index")
    vec_kwargs = dict(vec_params or {})
    # Keep vector store location aligned to settings paths.
    # This matters for local tests and MCP tools.
    if vec_provider_id == "vector.chroma_lite" and "db_path" not in vec_kwargs:
        vec_kwargs["db_path"] = str(settings.paths.chroma_dir / "chroma_lite.sqlite")
    if vec_provider_id == "vector.chroma" and "persist_dir" not in vec_kwargs:
        vec_kwargs["persist_dir"] = str(settings.paths.chroma_dir / "chroma")
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
    rerank_profile_id: str | None = None
    try:
        reranker_provider_id, reranker_params = strategy.resolve_provider("reranker")
        rerank_profile_id = _resolve_rerank_profile_id(reranker_provider_id, reranker_params)
        if reranker_provider_id not in {"noop", "reranker.noop"}:
            try:
                reranker = registry.create(
                    "reranker",
                    reranker_provider_id,
                    **(reranker_params or {}),
                )
            except Exception as e:
                # Keep rerank stage observable: fallback warning should be emitted in stage.rerank.
                reranker = _InitErrorReranker(provider_id=reranker_provider_id, err_message=str(e))
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
        reranker_provider_id=reranker_provider_id,
        rerank_profile_id=rerank_profile_id,
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

    def _meta(kind: str, provider_id: str, params: dict | None) -> dict[str, Any]:
        params = params or {}
        profile_id = params.get("profile_id") or params.get("text_norm_profile_id")
        version = params.get("version") or params.get("model_version")
        meta = {"provider_id": provider_id}
        if profile_id:
            meta["profile_id"] = str(profile_id)
        if version:
            meta["version"] = str(version)
        if kind == "reranker":
            rerank_profile_id = _resolve_rerank_profile_id(provider_id, params)
            if rerank_profile_id:
                meta["rerank_profile_id"] = rerank_profile_id
        return meta

    snapshot: dict[str, dict[str, Any]] = {}

    embedder_provider_id, embedder_params = strategy.resolve_provider("embedder")
    snapshot["embedder"] = _meta("embedder", embedder_provider_id, embedder_params)
    snapshot["vector_index"] = _meta("vector_index", vec_provider_id, vec_params)
    snapshot["retriever"] = _meta("retriever", retriever_provider_id, retriever_params)

    try:
        llm_provider_id, llm_params = strategy.resolve_provider("llm")
        snapshot["llm"] = _meta("llm", llm_provider_id, llm_params)
    except Exception:
        pass

    if sparse_provider_id:
        snapshot["sparse_retriever"] = _meta("sparse_retriever", sparse_provider_id, sparse_params)
    if fusion_provider_id:
        snapshot["fusion"] = _meta("fusion", fusion_provider_id, fusion_params)
    if reranker_provider_id:
        snapshot["reranker"] = _meta("reranker", reranker_provider_id, reranker_params)

    ctx.providers_snapshot = snapshot


def _resolve_rerank_profile_id(provider_id: str | None, params: dict | None) -> str | None:
    if not provider_id:
        return None
    raw = None
    if isinstance(params, dict):
        raw = (
            params.get("rerank_profile_id")
            or params.get("profile_id")
            or params.get("text_profile_id")
        )
    if raw is not None:
        text = str(raw).strip()
        if text:
            return text
    return f"{provider_id}.default"
