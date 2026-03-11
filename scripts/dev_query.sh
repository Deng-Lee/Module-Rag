#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERBOSE=0
POSITIONAL=()
for arg in "$@"; do
  case "$arg" in
    --verbose)
      VERBOSE=1
      ;;
    -h|--help)
      echo "usage: scripts/dev_query.sh \"your question\" [strategy_config_id] [top_k] [--verbose]"
      exit 0
      ;;
    *)
      POSITIONAL+=("$arg")
      ;;
  esac
done

QUERY="${POSITIONAL[0]:-}"
STRATEGY_ID="${POSITIONAL[1]:-local.default}"
TOP_K="${POSITIONAL[2]:-5}"

if [[ -z "$QUERY" ]]; then
  echo "usage: scripts/dev_query.sh \"your question\" [strategy_config_id] [top_k] [--verbose]"
  exit 2
fi

PYTHONPATH=. .venv/bin/python - "$QUERY" "$STRATEGY_ID" "$TOP_K" "$VERBOSE" <<'PY'
import json
import os
import sys
from src.core.strategy import load_settings
from src.observability.sinks.jsonl import JsonlSink
from src.observability.obs import set_sink

from src.core.runners.query import QueryRunner

query = sys.argv[1]
strategy_id = sys.argv[2]
limit = int(sys.argv[3])
verbose = sys.argv[4] == "1"

settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
runner = QueryRunner(settings_path=settings_path)
settings = load_settings(settings_path)
set_sink(JsonlSink(settings.paths.logs_dir))

resp = runner.run(query, strategy_config_id=strategy_id, top_k=limit)
print(resp.content_md)
print(json.dumps(resp.structured, ensure_ascii=False, indent=2))
if verbose:
    trace = resp.trace
    verbose_payload = {
        "query": query,
        "strategy_config_id": strategy_id,
        "top_k": limit,
        "trace_id": resp.trace_id,
        "source_count": len(resp.sources),
        "sources": [
            {
                "rank": s.rank,
                "chunk_id": s.chunk_id,
                "doc_id": s.doc_id,
                "score": s.score,
                "source": s.source,
                "section_path": s.section_path,
                "chunk_index": s.chunk_index,
                "asset_ids": list(s.asset_ids or []),
            }
            for s in resp.sources
        ],
        "providers": getattr(trace, "providers", {}) if trace is not None else {},
        "aggregates": getattr(trace, "aggregates", {}) if trace is not None else {},
        "spans": [
            {
                "span": getattr(span, "name", ""),
                "event_kinds": [str(getattr(ev, "kind", "") or "") for ev in getattr(span, "events", []) or []],
            }
            for span in (getattr(trace, "spans", None) or [])
        ],
    }
    print("=== VERBOSE DETAILS BEGIN ===")
    print(json.dumps(verbose_payload, ensure_ascii=False, indent=2))
    print("=== VERBOSE DETAILS END ===")
print(f"trace_id: {resp.trace_id}")
PY
