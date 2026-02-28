from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..jsonrpc.codec import INVALID_PARAMS
from ..jsonrpc.dispatcher import JsonRpcAppError
from ..errors import DEADLINE_EXCEEDED, attach_trace_id
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
        # Per-call view: ensure errors can be attributed to a call-scoped trace_id.
        call_session = session.new_call()
        if call_session.deadline_ts is not None:
            import time

            if time.time() >= call_session.deadline_ts:
                raise JsonRpcAppError(
                    DEADLINE_EXCEEDED,
                    "deadline exceeded",
                    {"trace_id": call_session.trace_id},
                )

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

        try:
            out = tool.call(call_session, args)
            return build_response_envelope(session=call_session, tool_name=name, output=out)
        except JsonRpcAppError as e:
            data = attach_trace_id(e.data, call_session.trace_id)
            raise JsonRpcAppError(e.code, e.message, data) from e
        except Exception as e:
            raise JsonRpcAppError(
                -32603,
                "internal error",
                {"trace_id": call_session.trace_id, "exc_type": type(e).__name__},
            ) from e
