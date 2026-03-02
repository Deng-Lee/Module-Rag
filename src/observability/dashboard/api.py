from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ...core.runners import AdminRunner, IngestRunner
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
    if not items and isinstance(reader, JsonlReader):
        traces = list(reader.iter_traces())
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
    if hasattr(reader, "list_traces"):
        items = reader.list_traces(
            limit=limit,
            offset=offset,
            trace_type=trace_type,
            strategy_config_id=strategy_config_id,
            status=status,
        )
    else:
        items = []
        for t in reader.iter_traces():
            if trace_type and t.trace_type != trace_type:
                continue
            if status and t.status != status:
                continue
            if strategy_config_id and t.strategy_config_id != strategy_config_id:
                continue
            items.append(
                {
                    "trace_id": t.trace_id,
                    "trace_type": t.trace_type,
                    "status": t.status,
                    "start_ts": t.start_ts,
                    "end_ts": t.end_ts,
                    "strategy_config_id": t.strategy_config_id,
                }
            )
        items = items[offset : offset + limit]
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
    return env.to_dict()


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
    }


@router.post("/ingest")
def post_ingest(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings(request)
    file_path = payload.get("file_path")
    policy = payload.get("policy", "skip")
    strategy_config_id = payload.get("strategy_config_id", settings.defaults.strategy_config_id)
    if not file_path:
        return {"status": "error", "reason": "missing file_path"}
    runner = IngestRunner(settings_path="config/settings.yaml")
    resp = runner.run(file_path, strategy_config_id=strategy_config_id, policy=str(policy))
    return {"status": "ok", "trace_id": resp.trace_id, "structured": resp.structured}


@router.post("/delete")
def post_delete(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings(request)
    doc_id = payload.get("doc_id")
    version_id = payload.get("version_id")
    mode = payload.get("mode", "soft")
    dry_run = bool(payload.get("dry_run", False))
    if not doc_id:
        return {"status": "error", "reason": "missing doc_id"}
    runner = AdminRunner(settings_path="config/settings.yaml")
    res = runner.delete_document(doc_id=doc_id, version_id=version_id, mode=str(mode), dry_run=dry_run)
    return {"status": res.status, "trace_id": res.trace_id, "affected": res.affected}


@router.post("/eval/run")
def post_run_eval(_: Request, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"status": "stub", "run_id": "eval_stub", "payload": payload or {}}


@router.get("/eval/runs")
def list_eval_runs(_: Request, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    return {"items": [], "limit": limit, "offset": offset}


@router.get("/eval/trends")
def eval_trends(_: Request, metric: str = "hit_rate@k", window: int = 30) -> dict[str, Any]:
    return {"metric": metric, "window": window, "points": []}
