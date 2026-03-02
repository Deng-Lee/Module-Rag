#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

FILE_PATH="${1:-}"
STRATEGY_ID="${2:-local.default}"
POLICY="${3:-new_version}"

if [[ -z "$FILE_PATH" ]]; then
  echo "usage: scripts/dev_ingest.sh <file_path> [strategy_config_id] [policy]"
  exit 2
fi

if [[ ! -f "$FILE_PATH" ]]; then
  echo "file not found: $FILE_PATH"
  exit 2
fi

PYTHONPATH=. .venv/bin/python - "$FILE_PATH" "$STRATEGY_ID" "$POLICY" <<'PY'
import json
import sys
from pathlib import Path

from src.core.runners.ingest import IngestRunner

file_path = Path(sys.argv[1])
strategy_id = sys.argv[2]
policy = sys.argv[3]

runner = IngestRunner()
resp = runner.run(file_path, strategy_config_id=strategy_id, policy=policy)
print(resp.content_md)
structured = dict(resp.structured or {})
md_path = structured.get("md_path")
if isinstance(md_path, str):
    try:
        root = Path.cwd().resolve()
        md_rel = str(Path(md_path).resolve().relative_to(root))
        structured["md_path"] = md_rel
    except Exception:
        pass
print(json.dumps(structured, ensure_ascii=False, indent=2))
print(f"trace_id: {resp.trace_id}")
PY
