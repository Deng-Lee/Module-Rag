#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

QUERY="${1:-}"
STRATEGY_ID="${2:-local.default}"
TOP_K="${3:-5}"

if [[ -z "$QUERY" ]]; then
  echo "usage: scripts/dev_query.sh \"your question\" [strategy_config_id] [top_k]"
  exit 2
fi

PYTHONPATH=. .venv/bin/python - "$QUERY" "$STRATEGY_ID" "$TOP_K" <<'PY'
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

settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
runner = QueryRunner(settings_path=settings_path)
settings = load_settings(settings_path)
set_sink(JsonlSink(settings.paths.logs_dir))

resp = runner.run(query, strategy_config_id=strategy_id, limit=limit)
print(resp.content_md)
print(json.dumps(resp.structured, ensure_ascii=False, indent=2))
print(f"trace_id: {resp.trace_id}")
PY
