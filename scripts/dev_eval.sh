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
      echo "usage: scripts/dev_eval.sh [dataset_id] [strategy_config_id] [top_k] [--verbose]"
      exit 0
      ;;
    *)
      POSITIONAL+=("$arg")
      ;;
  esac
done

DATASET_ID="${POSITIONAL[0]:-rag_eval_small}"
STRATEGY_ID="${POSITIONAL[1]:-local.default}"
TOP_K="${POSITIONAL[2]:-5}"

PYTHONPATH=. .venv/bin/python - "$DATASET_ID" "$STRATEGY_ID" "$TOP_K" "$VERBOSE" <<'PY'
import json
import os
import sys

from src.core.strategy import load_settings
from src.observability.sinks.jsonl import JsonlSink
from src.observability.obs import set_sink
from src.core.runners.eval import EvalRunner

dataset_id = sys.argv[1]
strategy_id = sys.argv[2]
top_k = int(sys.argv[3])
verbose = sys.argv[4] == "1"

settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
# Ensure observability sink writes traces for CLI runs
settings = load_settings(settings_path)
set_sink(JsonlSink(settings.paths.logs_dir))

runner = EvalRunner(settings_path=settings_path)
result = runner.run(dataset_id, strategy_config_id=strategy_id, top_k=top_k)
print(json.dumps({"run_id": result.run_id, "metrics": result.metrics}, ensure_ascii=False, indent=2))
for case in result.cases:
    print(f"case_id={case.case_id} trace_id={case.trace_id}")
if verbose:
    verbose_payload = {
        "dataset_arg": dataset_id,
        "dataset_id": result.dataset_id,
        "strategy_config_id": strategy_id,
        "top_k": top_k,
        "run_id": result.run_id,
        "metrics": result.metrics,
        "cases": [
            {
                "case_id": case.case_id,
                "trace_id": case.trace_id,
                "metrics": case.metrics,
                "artifacts": case.artifacts,
            }
            for case in result.cases
        ],
    }
    print("=== VERBOSE DETAILS BEGIN ===")
    print(json.dumps(verbose_payload, ensure_ascii=False, indent=2))
    print("=== VERBOSE DETAILS END ===")
PY
