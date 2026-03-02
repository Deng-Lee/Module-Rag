#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHONPATH=. .venv/bin/python - <<'PY'
import json
from pathlib import Path

from src.observability.obs import api as obs
from src.observability.trace.context import TraceContext


def _normalize_trace(rec: dict) -> dict:
    rec = dict(rec)
    rec["start_ts"] = 0.0
    rec["end_ts"] = 0.0
    for s in rec.get("spans", []):
        s["span_id"] = "span_fixed"
        s["start_ts"] = 0.0
        s["end_ts"] = 0.0
        for ev in s.get("events", []):
            ev["ts"] = 0.0
    rec["aggregates"] = {
        "latency_ms": 0.0,
        "stage_latency_ms": {"stage.query_norm": 0.0},
        "counters": {},
        "errors": [],
    }
    return rec


def _make_trace() -> dict:
    ctx = TraceContext.new("trace_golden_query", trace_type="query", strategy_config_id="local.default")
    ctx.providers_snapshot = {"embedder": {"provider_id": "embedder.fake"}}
    with TraceContext.activate(ctx):
        with obs.with_stage("query_norm"):
            obs.event("query.normalized", {"query_hash": "h", "rewrite_used": False})
        ctx.replay_keys["query_hash"] = "h"
        env = ctx.finish()
    return env.to_dict()


golden = _normalize_trace(_make_trace())
path = Path("tests/golden/trace_query.json")
path.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"golden updated: {path}")
PY
