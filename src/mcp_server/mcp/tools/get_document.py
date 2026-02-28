from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.strategy import load_settings
from ...jsonrpc.codec import INTERNAL_ERROR, INVALID_PARAMS
from ...jsonrpc.dispatcher import JsonRpcAppError
from ..session import McpSession
from .base import FunctionTool, ToolSpec


@dataclass
class GetDocumentToolConfig:
    settings_path: str | Path = "config/settings.yaml"
    default_max_chars: int = 200_000
    hard_max_chars: int = 1_000_000


def _resolve_md_norm_path(*, settings_path: str | Path, doc_id: str, version_id: str) -> Path:
    settings = load_settings(settings_path)
    return (settings.paths.md_dir / doc_id / version_id / "md_norm.md").resolve()


def _read_text_limited(p: Path, *, max_chars: int) -> tuple[str, bool]:
    text = p.read_text(encoding="utf-8", errors="replace")
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def make_tool(*, cfg: GetDocumentToolConfig | None = None) -> FunctionTool:
    cfg = cfg or GetDocumentToolConfig()

    def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        _ = session
        doc_id = args.get("doc_id")
        version_id = args.get("version_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise JsonRpcAppError(INVALID_PARAMS, "missing required param: doc_id")
        if not isinstance(version_id, str) or not version_id:
            raise JsonRpcAppError(INVALID_PARAMS, "missing required param: version_id")

        max_chars = args.get("max_chars", cfg.default_max_chars)
        if isinstance(max_chars, bool) or not isinstance(max_chars, int):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_chars must be integer")
        if max_chars < 1:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_chars must be positive")
        if max_chars > cfg.hard_max_chars:
            max_chars = cfg.hard_max_chars

        md_path = _resolve_md_norm_path(settings_path=cfg.settings_path, doc_id=doc_id, version_id=version_id)
        if not md_path.exists():
            raise JsonRpcAppError(INVALID_PARAMS, "document not found", {"doc_id": doc_id, "version_id": version_id})

        try:
            md_text, truncated = _read_text_limited(md_path, max_chars=max_chars)
        except Exception as e:
            raise JsonRpcAppError(INTERNAL_ERROR, "failed to read document", {"exc_type": type(e).__name__}) from e

        warnings: list[str] = []
        if truncated:
            warnings.append("document_truncated")

        # L0 text-first: return the document as markdown.
        # L1/L2: attach structured fields for UI navigation.
        return {
            "text": md_text,
            "structured": {
                "doc_id": doc_id,
                "version_id": version_id,
                "warnings": warnings,
                # Do not return absolute paths; they are internal.
            },
        }

    return FunctionTool(
        spec=ToolSpec(
            name="library.get_document",
            description="Fetch the normalized markdown (facts layer) for a doc_id/version_id.",
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "version_id": {"type": "string"},
                    "max_chars": {"type": "integer"},
                },
                "required": ["doc_id", "version_id"],
                "additionalProperties": False,
            },
        ),
        fn=_handler,
    )

