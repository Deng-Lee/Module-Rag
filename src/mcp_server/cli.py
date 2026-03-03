from __future__ import annotations

import argparse
import os
from pathlib import Path

from .entry import serve_stdio


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="module-rag-mcp",
        description="MODULE-RAG MCP server (stdio).",
    )
    p.add_argument(
        "--settings",
        dest="settings_path",
        default=None,
        help=(
            "Path to settings.yaml. Defaults to $MODULE_RAG_SETTINGS_PATH or "
            "config/settings.yaml."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    settings_path = (
        args.settings_path
        or os.environ.get("MODULE_RAG_SETTINGS_PATH")
        or "config/settings.yaml"
    )
    serve_stdio(Path(settings_path))


if __name__ == "__main__":  # pragma: no cover
    main()

