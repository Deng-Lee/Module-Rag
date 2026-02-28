from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.runners.admin import AdminRunner
from ...jsonrpc.codec import INTERNAL_ERROR, INVALID_PARAMS
from ...jsonrpc.dispatcher import JsonRpcAppError
from ..session import McpSession
from .base import FunctionTool, ToolSpec


@dataclass
class DeleteDocumentToolConfig:
    settings_path: str | Path = "config/settings.yaml"


def make_tool(*, cfg: DeleteDocumentToolConfig | None = None) -> FunctionTool:
    cfg = cfg or DeleteDocumentToolConfig()

    def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        _ = session
        doc_id = args.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise JsonRpcAppError(INVALID_PARAMS, "missing required param: doc_id")

        version_id = args.get("version_id")
        if version_id is not None and (not isinstance(version_id, str) or not version_id):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: version_id must be non-empty string")

        mode = args.get("mode", "soft")
        if not isinstance(mode, str) or mode not in {"soft", "hard"}:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: mode must be soft|hard")
        if mode != "soft":
            raise JsonRpcAppError(INVALID_PARAMS, "hard delete is not enabled in E-9")

        reason = args.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: reason must be string")

        dry_run = bool(args.get("dry_run", False))

        try:
            res = AdminRunner(settings_path=cfg.settings_path).delete_document(
                doc_id=doc_id,
                version_id=version_id,
                mode=mode,
                dry_run=dry_run,
            )
        except Exception as e:
            raise JsonRpcAppError(INTERNAL_ERROR, "delete failed", {"exc_type": type(e).__name__}) from e

        target = {"doc_id": doc_id}
        if version_id:
            target["version_id"] = version_id

        deleted = {"doc_id": doc_id, "version_ids": []}
        if version_id:
            deleted["version_ids"] = [version_id]

        text_lines = [
            f"Delete ({res.mode}) finished.",
            f"- status: {res.status}",
            f"- doc_id: {doc_id}",
            f"- version_id: {version_id or '(all)'}",
            f"- dry_run: {dry_run}",
        ]
        if reason:
            text_lines.append(f"- reason: {reason}")
        if res.warnings:
            text_lines.append(f"- warnings: {', '.join(res.warnings)}")

        return {
            "text": "\n".join(text_lines),
            "structured": {
                "status": res.status,
                "mode": res.mode,
                "target": target,
                "deleted": deleted,
                "affected": res.affected,
                "warnings": res.warnings,
            },
        }

    return FunctionTool(
        spec=ToolSpec(
            name="library.delete_document",
            description="Soft delete a document (or a specific version).",
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "version_id": {"type": "string"},
                    "mode": {"type": "string"},
                    "reason": {"type": "string"},
                    "dry_run": {"type": "boolean"},
                },
                "required": ["doc_id"],
                "additionalProperties": False,
            },
        ),
        fn=_handler,
    )
