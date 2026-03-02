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
import sys

from src.core.runners.query import QueryRunner

query = sys.argv[1]
strategy_id = sys.argv[2]
top_k = int(sys.argv[3])

runner = QueryRunner()
resp = runner.run(query, strategy_config_id=strategy_id, top_k=top_k)
print(resp.content_md)
print(json.dumps(resp.structured, ensure_ascii=False, indent=2))
print(f"trace_id: {resp.trace_id}")
PY
