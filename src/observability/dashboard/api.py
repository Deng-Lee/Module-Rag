from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Request

from ...core.runners import AdminRunner, EvalRunner, IngestRunner, QueryRunner
from ...core.strategy import Settings
from ...ingestion.stages.storage.sqlite import SqliteStore
from ..readers.jsonl_reader import JsonlReader
from ..readers.sqlite_reader import SqliteTraceReader
from .deps import get_settings, get_sqlite_store, get_trace_reader


router = APIRouter(prefix="/api")


def _get_reader(settings: Settings) -> Any:
    return get_trace_reader(settings)


def _overview_from_traces(reader: Any) -> dict[str, Any]:
    items = reader.list_traces(limit=10, offset=0) if hasattr(reader, "list_traces") else []
    trace0 = None
    if not items and isinstance(reader, JsonlReader):
        traces = list(reader.iter_traces())
        trace0 = traces[0] if traces else None
        items = [
            {
                "trace_id": t.trace_id,
                "trace_type": t.trace_type,
                "status": t.status,
                "start_ts": t.start_ts,
                "end_ts": t.end_ts,
                "strategy_config_id": t.strategy_config_id,
            }
            for t in traces[:10]
        ]

    total = len(items)
    errors = len([it for it in items if it.get("status") == "error"])
    avg_latency = 0.0
    providers: dict[str, Any] = {}

    if items:
        if trace0 is not None:
            providers = trace0.providers
            if trace0.aggregates and "latency_ms" in trace0.aggregates:
                avg_latency = float(trace0.aggregates.get("latency_ms") or 0.0)
        else:
            trace_id = items[0]["trace_id"]
            t = reader.get_trace(trace_id) if hasattr(reader, "get_trace") else None
            if t is not None:
                providers = t.providers
                if t.aggregates and "latency_ms" in t.aggregates:
                    avg_latency = float(t.aggregates.get("latency_ms") or 0.0)

    return {
        "recent_traces": total,
        "error_rate": (errors / total) if total else 0.0,
        "avg_latency_ms": avg_latency,
        "providers": providers,
    }


@router.get("/overview")
def overview(request: Request) -> dict[str, Any]:
    settings = get_settings(request)
    reader = _get_reader(settings)
    sqlite = get_sqlite_store(settings)

    assets = {
        "docs": sqlite.count_docs(),
        "chunks": sqlite.count_chunks(),
        "assets": sqlite.count_assets(),
    }
    health = _overview_from_traces(reader)
    return {
        "assets": assets,
        "health": health,
        "providers": health.get("providers", {}),
    }


@router.get("/traces")
def list_traces(
    request: Request,
    trace_type: str | None = None,
    strategy_config_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    settings = get_settings(request)
    reader = _get_reader(settings)
    # Get raw items from reader (sqlite reader exposes list_traces; jsonl reader we iterate)
    if hasattr(reader, "list_traces"):
        raw_items = reader.list_traces(
            limit=limit,
            offset=0,
            trace_type=trace_type,
            strategy_config_id=strategy_config_id,
            status=status,
        )
    else:
        raw_items = []
        for t in reader.iter_traces():
            if trace_type and t.trace_type != trace_type:
                continue
            if status and t.status != status:
                continue
            if strategy_config_id and t.strategy_config_id != strategy_config_id:
                continue
            raw_items.append(
                {
                    "trace_id": t.trace_id,
                    "trace_type": t.trace_type,
                    "status": t.status,
                    "start_ts": t.start_ts,
                    "end_ts": t.end_ts,
                    "strategy_config_id": t.strategy_config_id,
                    # try to extract a simple error summary if available
                    "_aggregates": getattr(t, "aggregates", None),
                }
            )

    # Enrich items with quick error metadata for UI: has_error, error_stage (if any)
    enriched: list[dict[str, Any]] = []
    for it in raw_items:
        has_error = (it.get("status") == "error")
        error_stage = None
        ag = it.get("_aggregates") or {}
        errs = ag.get("errors") if isinstance(ag, dict) else None
        if isinstance(errs, list) and errs:
            first = errs[0]
            error_stage = first.get("stage") if isinstance(first, dict) else None
        enriched.append({
            "trace_id": it.get("trace_id"),
            "trace_type": it.get("trace_type"),
            "status": it.get("status"),
            "start_ts": it.get("start_ts"),
            "end_ts": it.get("end_ts"),
            "strategy_config_id": it.get("strategy_config_id"),
            "has_error": has_error,
            "error_stage": error_stage,
        })

    # Order: error traces first, then by start_ts desc
    enriched.sort(key=lambda x: ((1 if x.get("has_error") else 0), float(x.get("start_ts") or 0.0)), reverse=True)

    # Apply offset/limit after ordering
    items = enriched[offset : offset + limit]
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/trace/{trace_id}")
def get_trace(request: Request, trace_id: str) -> dict[str, Any]:
    settings = get_settings(request)
    reader = _get_reader(settings)
    env = reader.get_trace(trace_id) if hasattr(reader, "get_trace") else None
    if env is None and hasattr(reader, "iter_traces"):
        for t in reader.iter_traces():
            if t.trace_id == trace_id:
                env = t
                break
    if env is None:
        return {"error": "not_found", "trace_id": trace_id}
    # Return trace envelope plus highlighted error events for quick review in dashboard
    env_dict = env.to_dict()
    error_kinds = {"stage.error", "error", "embedder.http_error", "embedder.request_error", "llm.http_error", "llm.request_error"}
    highlighted: list[dict[str, Any]] = []

    # scan spans' events
    for s in env.spans:
        for ev in s.events:
            kind = getattr(ev, "kind", None)
            if not isinstance(kind, str):
                continue
            if any(k in kind for k in ("error",)) or kind in error_kinds:
                highlighted.append({"span": s.name, "ts": ev.ts, "kind": kind, "attrs": ev.attrs})

    # scan trace-level events
    for ev in env.events:
        kind = getattr(ev, "kind", None)
        if not isinstance(kind, str):
            continue
        if any(k in kind for k in ("error",)) or kind in error_kinds:
            highlighted.append({"span": None, "ts": ev.ts, "kind": kind, "attrs": ev.attrs})

    # trim long response snippets in attrs to 1000 chars to keep payload reasonable
    for he in highlighted:
        attrs = he.get("attrs") or {}
        if isinstance(attrs.get("response_snippet"), str) and len(attrs["response_snippet"]) > 1000:
            attrs["response_snippet"] = attrs["response_snippet"][:1000]

    return {"trace": env_dict, "error_events": highlighted[:20]}


@router.get("/documents")
def list_documents(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    include_deleted: bool = False,
    doc_id: str | None = None,
) -> dict[str, Any]:
    settings = get_settings(request)
    sqlite = get_sqlite_store(settings)
    items = sqlite.list_doc_versions(
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
        doc_id=doc_id,
    )
    return {"items": items, "limit": limit, "offset": offset, "include_deleted": include_deleted}


@router.get("/chunk/{chunk_id}")
def get_chunk(request: Request, chunk_id: str) -> dict[str, Any]:
    settings = get_settings(request)
    sqlite = get_sqlite_store(settings)
    rows = sqlite.fetch_chunks([chunk_id])
    row = rows[0] if rows else None
    assets = sqlite.fetch_chunk_assets([chunk_id]).get(chunk_id, [])
    enrich_chunk = sqlite.fetch_chunk_enrichments([chunk_id]).get(chunk_id, {})
    enrich_assets = sqlite.fetch_asset_enrichments(assets) if assets else {}
    if row is None:
        return {"error": "not_found", "chunk_id": chunk_id}
    return {
        "chunk_id": row.chunk_id,
        "doc_id": row.doc_id,
        "version_id": row.version_id,
        "section_id": row.section_id,
        "section_path": row.section_path,
        "chunk_index": row.chunk_index,
        "chunk_text": row.chunk_text,
        "asset_ids": assets,
        "enrichments": {
            "chunk": enrich_chunk,
            "assets": enrich_assets,
        },
    }


@router.post("/ingest")
def post_ingest(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings(request)
    file_path = payload.get("file_path")
    policy = payload.get("policy", "skip")
    strategy_config_id = payload.get("strategy_config_id", settings.defaults.strategy_config_id)
    if not file_path:
        return {"status": "error", "reason": "missing file_path"}
    if isinstance(policy, str) and policy.strip().lower() == "default":
        policy = "skip"
    if isinstance(strategy_config_id, str) and strategy_config_id.strip().lower() == "default":
        strategy_config_id = settings.defaults.strategy_config_id
    # Respect per-run settings (QA clean dirs) via env to avoid writing into default data/.
    settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
    runner = IngestRunner(settings_path=settings_path)
    resp = runner.run(file_path, strategy_config_id=strategy_config_id, policy=str(policy))
    return {"status": "ok", "trace_id": resp.trace_id, "structured": resp.structured}


@router.post("/query")
def post_query(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings(request)
    query = str(payload.get("query") or "").strip()
    if not query:
        return {"status": "error", "reason": "missing query"}

    top_k_raw = payload.get("top_k", 5)
    try:
        top_k = int(top_k_raw)
    except Exception:
        return {"status": "error", "reason": "invalid top_k"}
    if top_k <= 0:
        return {"status": "error", "reason": "top_k must be > 0"}

    strategy_config_id = payload.get("strategy_config_id", settings.defaults.strategy_config_id)
    if isinstance(strategy_config_id, str) and strategy_config_id.strip().lower() == "default":
        strategy_config_id = settings.defaults.strategy_config_id

    settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
    runner = QueryRunner(settings_path=settings_path)
    resp = runner.run(query, strategy_config_id=str(strategy_config_id), top_k=top_k)
    sources = [
        {
            "chunk_id": s.chunk_id,
            "doc_id": s.doc_id,
            "version_id": s.version_id,
            "section_path": s.section_path,
            "page_range": s.page_range,
            "score": s.score,
            "asset_ids": list(s.asset_ids or []),
        }
        for s in resp.sources
    ]
    return {
        "status": "ok",
        "trace_id": resp.trace_id,
        "content_md": resp.content_md,
        "sources": sources,
    }


@router.post("/delete")
def post_delete(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings(request)
    doc_id = payload.get("doc_id")
    version_id = payload.get("version_id")
    mode = payload.get("mode", "soft")
    dry_run = bool(payload.get("dry_run", False))
    if not doc_id:
        return {"status": "error", "reason": "missing doc_id"}
    if isinstance(mode, str) and mode.strip().lower() == "default":
        mode = "soft"
    settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
    runner = AdminRunner(settings_path=settings_path)
    res = runner.delete_document(doc_id=doc_id, version_id=version_id, mode=str(mode), dry_run=dry_run)
    return {"status": res.status, "trace_id": res.trace_id, "affected": res.affected}


@router.post("/eval/run")
def post_run_eval(request: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings(request)
    payload = payload or {}
    dataset_id = payload.get("dataset_id", "rag_eval_small")
    strategy_config_id = payload.get("strategy_config_id", settings.defaults.strategy_config_id)
    top_k = payload.get("top_k", 5)
    judge_strategy_id = payload.get("judge_strategy_id")

    try:
        runner = EvalRunner(settings_path=os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml"), settings=settings)
        result = runner.run(
            dataset_id=str(dataset_id),
            strategy_config_id=str(strategy_config_id),
            top_k=int(top_k),
            judge_strategy_id=str(judge_strategy_id) if judge_strategy_id else None,
        )
        return {
            "status": "ok",
            "run_id": result.run_id,
            "dataset_id": result.dataset_id,
            "strategy_config_id": result.strategy_config_id,
            "metrics": result.metrics,
            "cases": [{"case_id": c.case_id, "trace_id": c.trace_id, "metrics": c.metrics} for c in result.cases],
        }
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}


@router.get("/eval/runs")
def list_eval_runs(request: Request, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    settings = get_settings(request)
    sqlite = get_sqlite_store(settings)
    items = sqlite.list_eval_runs(limit=limit, offset=offset)
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/eval/trends")
def eval_trends(_: Request, metric: str = "hit_rate@k", window: int = 30) -> dict[str, Any]:
    return {"metric": metric, "window": window, "points": []}
