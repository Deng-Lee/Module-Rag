from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..jsonrpc.codec import INVALID_PARAMS
from ..jsonrpc.dispatcher import JsonRpcAppError
from .session import McpSession
from .tools.registry import ToolRegistry


@dataclass
class McpProtocol:
    """MCP semantic layer (E-3 scope).

    This layer does not care about transport (stdio/http). It exposes handlers
    for MCP methods, and delegates tool execution to ToolRegistry.
    """

    tools: ToolRegistry
    server_name: str = "module-rag"
    server_version: str = "0.1"
    protocol_version: str = "0.1"

    def handle_initialize(self, params: dict[str, Any] | None) -> dict[str, Any]:
        _ = params or {}
        return {
            "protocolVersion": self.protocol_version,
            "serverInfo": {"name": self.server_name, "version": self.server_version},
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False},
            },
        }

    def handle_tools_list(self, session: McpSession) -> dict[str, Any]:
        _ = session
        return {"tools": self.tools.list_specs()}

    def handle_tools_call(self, session: McpSession, name: str, args: dict[str, Any] | None) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            raise JsonRpcAppError(INVALID_PARAMS, f"unknown tool: {name}")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise JsonRpcAppError(INVALID_PARAMS, "tool args must be an object")
        return tool.call(session, args)

