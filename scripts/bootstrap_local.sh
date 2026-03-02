#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bootstrap_local() {
  mkdir -p \
    data/raw \
    data/md \
    data/assets \
    data/chroma \
    data/sqlite \
    cache \
    logs

  # Keep empty dirs in git if needed (ignored by default .gitignore, but helps local UX).
  : > data/raw/.gitkeep
  : > data/md/.gitkeep
  : > data/assets/.gitkeep
  : > data/chroma/.gitkeep
  : > data/sqlite/.gitkeep
  : > cache/.gitkeep
  : > logs/.gitkeep
}

bootstrap_local
echo "bootstrap_local: OK"

echo ""
echo "Next steps:"
echo "  1) scripts/dev_ingest.sh <path-to-doc>"
echo "  2) scripts/dev_query.sh \"your question\""
echo "  3) scripts/dev_dashboard.sh"
echo "  4) scripts/dev_eval.sh rag_eval_small"
