#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DATASET_ID="${1:-rag_eval_small}"
STRATEGY_ID="${2:-local.default}"
TOP_K="${3:-5}"

PYTHONPATH=. .venv/bin/python - "$DATASET_ID" "$STRATEGY_ID" "$TOP_K" <<'PY'
import json
import sys

from src.core.runners.eval import EvalRunner

dataset_id = sys.argv[1]
strategy_id = sys.argv[2]
top_k = int(sys.argv[3])

runner = EvalRunner()
result = runner.run(dataset_id, strategy_config_id=strategy_id, top_k=top_k)
print(json.dumps({"run_id": result.run_id, "metrics": result.metrics}, ensure_ascii=False, indent=2))
for case in result.cases:
    print(f"case_id={case.case_id} trace_id={case.trace_id}")
PY
