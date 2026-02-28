from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.runners import IngestRunner
from ....core.strategy import load_settings
from ...jsonrpc.codec import INTERNAL_ERROR, INVALID_PARAMS
from ...jsonrpc.dispatcher import JsonRpcAppError
from ..session import McpSession
from .base import FunctionTool, ToolSpec


@dataclass
class IngestToolConfig:
    settings_path: str | Path = "config/settings.yaml"


def normalize_ingest_input(args: dict[str, Any], *, cfg: IngestToolConfig) -> tuple[str, str, str]:
    file_path = args.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        raise JsonRpcAppError(INVALID_PARAMS, "missing required param: file_path")

    policy = args.get("policy", "skip")
    if not isinstance(policy, str) or policy not in {"skip", "new_version", "continue"}:
        raise JsonRpcAppError(INVALID_PARAMS, "invalid param: policy must be one of skip|new_version|continue")

    strategy_config_id = args.get("strategy_config_id")
    if strategy_config_id is None:
        settings = load_settings(cfg.settings_path)
        strategy_config_id = settings.defaults.strategy_config_id
    if not isinstance(strategy_config_id, str) or not strategy_config_id:
        raise JsonRpcAppError(INVALID_PARAMS, "invalid param: strategy_config_id must be non-empty string")

    return file_path, policy, strategy_config_id


def make_tool(*, runner: IngestRunner, cfg: IngestToolConfig | None = None) -> FunctionTool:
    cfg = cfg or IngestToolConfig(settings_path=runner.settings_path)

    def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        _ = session
        file_path, policy, strategy_config_id = normalize_ingest_input(args, cfg=cfg)
        resp = runner.run(file_path, strategy_config_id=strategy_config_id, policy=policy)
        if resp.structured.get("status") == "error":
            # Fail the tool call so clients can treat ingestion as a command that either succeeds or fails.
            raise JsonRpcAppError(INTERNAL_ERROR, "ingest failed", resp.structured)
        return resp

    return FunctionTool(
        spec=ToolSpec(
            name="library.ingest",
            description="Ingest a local document (pdf/md) into the library (dedup→chunk→embed→upsert).",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "policy": {"type": "string"},
                    "strategy_config_id": {"type": "string"},
                },
                "required": ["file_path"],
                "additionalProperties": False,
            },
        ),
        fn=_handler,
    )
