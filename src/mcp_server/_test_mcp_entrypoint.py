from __future__ import annotations

from src.mcp_server.jsonrpc import Dispatcher, JsonRpcRequest, StdioTransport
from src.mcp_server.errors import map_exception_to_jsonrpc
from src.mcp_server.mcp import McpProtocol, McpSession
from src.mcp_server.mcp.tools.ping import tool as ping_tool
from src.mcp_server.mcp.tools.registry import ToolRegistry


def main() -> None:
    session = McpSession.new(client_level="L0")
    tools = ToolRegistry()
    tools.register(ping_tool)
    proto = McpProtocol(tools=tools)

    disp = Dispatcher()
    disp.error_mapper = map_exception_to_jsonrpc

    def initialize(req: JsonRpcRequest):
        return proto.handle_initialize(req.params if isinstance(req.params, dict) else None)

    def tools_list(req: JsonRpcRequest):
        return proto.handle_tools_list(session)

    def tools_call(req: JsonRpcRequest):
        params = req.params if isinstance(req.params, dict) else {}
        name = params.get("name")
        args = params.get("arguments")
        timeout_ms = params.get("timeout_ms")
        if not isinstance(name, str) or not name:
            raise ValueError("missing tool name")
        sess = session
        if isinstance(timeout_ms, int) and not isinstance(timeout_ms, bool):
            sess = sess.with_deadline(timeout_ms)
        return proto.handle_tools_call(sess, name=name, args=args)

    disp.register("initialize", initialize)
    disp.register("tools/list", tools_list)
    disp.register("tools/call", tools_call)

    StdioTransport().serve_requests(disp.handle)


if __name__ == "__main__":  # pragma: no cover
    main()
