from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.strategy import load_settings
from ....ingestion.stages.storage.sqlite import SqliteStore
from ...jsonrpc.codec import INVALID_PARAMS
from ...jsonrpc.dispatcher import JsonRpcAppError
from ..session import McpSession
from .base import FunctionTool, ToolSpec


@dataclass
class ListDocumentsToolConfig:
    settings_path: str | Path = "config/settings.yaml"
    default_limit: int = 20
    hard_max_limit: int = 200


def make_tool(*, cfg: ListDocumentsToolConfig | None = None) -> FunctionTool:
    cfg = cfg or ListDocumentsToolConfig()

    def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        _ = session
        limit = args.get("limit", cfg.default_limit)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: limit must be integer")
        if limit < 1:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: limit must be positive")
        if limit > cfg.hard_max_limit:
            limit = cfg.hard_max_limit

        offset = args.get("offset", 0)
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: offset must be integer")
        if offset < 0:
            offset = 0

        include_deleted = bool(args.get("include_deleted", False))

        doc_id = args.get("doc_id")
        if doc_id is not None and (not isinstance(doc_id, str) or not doc_id):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: doc_id must be non-empty string")

        settings = load_settings(cfg.settings_path)
        sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")

        items = sqlite.list_doc_versions(
            limit=limit,
            offset=offset,
            include_deleted=include_deleted,
            doc_id=doc_id,
        )

        text_lines = [
            "Documents (versions).",
            f"- count: {len(items)}",
            f"- limit: {limit}",
            f"- offset: {offset}",
            f"- include_deleted: {include_deleted}",
        ]
        if doc_id:
            text_lines.append(f"- doc_id: {doc_id}")
        return {
            "text": "\n".join(text_lines),
            "structured": {
                "items": items,
                "limit": limit,
                "offset": offset,
                "include_deleted": include_deleted,
            },
        }

    return FunctionTool(
        spec=ToolSpec(
            name="library.list_documents",
            description="List document versions (admin).",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                    "offset": {"type": "integer"},
                    "include_deleted": {"type": "boolean"},
                    "doc_id": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        fn=_handler,
    )

