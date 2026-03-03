from __future__ import annotations

from typing import Any

from .base import FunctionTool, ToolSpec
from ..session import McpSession


def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
    msg = args.get("message")
    if not isinstance(msg, str):
        msg = "pong"
    text = f"[{session.client_level}] {msg}"
    return {"text": text}


tool = FunctionTool(
    spec=ToolSpec(
        name="library_ping",
        description="Health check / smoke tool for MCP transport.",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            # Be permissive: some clients/models may attach extra fields when bridging tool calls.
            "additionalProperties": True,
        },
    ),
    fn=_handler,
)
