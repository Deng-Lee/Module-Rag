from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.runners import QueryRunner
from ....core.strategy import load_settings
from ...jsonrpc.codec import INTERNAL_ERROR, INVALID_PARAMS
from ...jsonrpc.dispatcher import JsonRpcAppError
from ..session import McpSession
from .base import FunctionTool, ToolSpec


@dataclass
class QueryToolConfig:
    settings_path: str | Path = "config/settings.yaml"


def normalize_query_input(
    args: dict[str, Any], *, cfg: QueryToolConfig
) -> tuple[str, str, int, dict[str, Any] | None]:
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise JsonRpcAppError(INVALID_PARAMS, "missing required param: query")

    top_k = args.get("top_k", 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise JsonRpcAppError(INVALID_PARAMS, "invalid param: top_k must be integer")
    if top_k < 1 or top_k > 50:
        raise JsonRpcAppError(INVALID_PARAMS, "invalid param: top_k must be in [1, 50]")

    filters = args.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise JsonRpcAppError(INVALID_PARAMS, "invalid param: filters must be an object")

    strategy_config_id = args.get("strategy_config_id")
    if strategy_config_id is None:
        settings = load_settings(cfg.settings_path)
        strategy_config_id = settings.defaults.strategy_config_id
    if not isinstance(strategy_config_id, str) or not strategy_config_id:
        raise JsonRpcAppError(INVALID_PARAMS, "invalid param: strategy_config_id must be non-empty string")

    return query, strategy_config_id, top_k, filters


def make_tool(*, runner: QueryRunner, cfg: QueryToolConfig | None = None) -> FunctionTool:
    cfg = cfg or QueryToolConfig(settings_path=runner.settings_path)

    def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        _ = session
        query, strategy_config_id, top_k, filters = normalize_query_input(args, cfg=cfg)
        try:
            return runner.run(query, strategy_config_id=strategy_config_id, top_k=top_k, filters=filters)
        except JsonRpcAppError:
            raise
        except Exception as e:
            raise JsonRpcAppError(INTERNAL_ERROR, "query failed", {"exc_type": type(e).__name__}) from e

    return FunctionTool(
        spec=ToolSpec(
            name="library.query",
            description="Query the library and return answer markdown + citations (no base64 assets).",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                    "filters": {"type": "object"},
                    "strategy_config_id": {"type": "string"},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        fn=_handler,
    )

