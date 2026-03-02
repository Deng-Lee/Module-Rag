#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${1:-127.0.0.1}"
PORT="${2:-7860}"

echo "Starting dashboard API on http://$HOST:$PORT"
export DASHBOARD_HOST="$HOST"
export DASHBOARD_PORT="$PORT"
PYTHONPATH=. .venv/bin/python - <<'PY'
import os
from pathlib import Path

import uvicorn

from src.core.strategy import load_settings
from src.observability.dashboard.app import create_app

settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
settings = load_settings(Path(settings_path))

host = os.environ.get("DASHBOARD_HOST", settings.server.dashboard_host)
port = int(os.environ.get("DASHBOARD_PORT", settings.server.dashboard_port))

app = create_app(settings)
uvicorn.run(app, host=host, port=port, log_level="info")
PY
