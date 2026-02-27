from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..jsonrpc.codec import INVALID_PARAMS
from ..jsonrpc.dispatcher import JsonRpcAppError
from .envelope import build_response_envelope
from .schema import SchemaValidationError, validate_tool_args
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

        # Validate args using tool spec schema.
        try:
            args = validate_tool_args(tool.spec.input_schema, args)
        except SchemaValidationError as e:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid params", {"message": str(e)}) from e

        out = tool.call(session, args)
        return build_response_envelope(session=session, tool_name=name, output=out)
