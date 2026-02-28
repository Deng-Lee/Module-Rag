from __future__ import annotations

import os

from src.core.runners import IngestRunner
from src.mcp_server.jsonrpc import Dispatcher, JsonRpcRequest, StdioTransport
from src.mcp_server.mcp import McpProtocol, McpSession
from src.mcp_server.mcp.tools.ingest import make_tool as make_ingest_tool
from src.mcp_server.mcp.tools.ping import tool as ping_tool
from src.mcp_server.mcp.tools.registry import ToolRegistry


def main() -> None:
    settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")

    session = McpSession.new(client_level="L1")
    tools = ToolRegistry()
    tools.register(ping_tool)
    tools.register(make_ingest_tool(runner=IngestRunner(settings_path=settings_path)))
    proto = McpProtocol(tools=tools)

    disp = Dispatcher()

    def initialize(req: JsonRpcRequest):
        return proto.handle_initialize(req.params if isinstance(req.params, dict) else None)

    def tools_list(req: JsonRpcRequest):
        return proto.handle_tools_list(session)

    def tools_call(req: JsonRpcRequest):
        params = req.params if isinstance(req.params, dict) else {}
        name = params.get("name")
        args = params.get("arguments")
        if not isinstance(name, str) or not name:
            raise ValueError("missing tool name")
        return proto.handle_tools_call(session, name=name, args=args)

    disp.register("initialize", initialize)
    disp.register("tools/list", tools_list)
    disp.register("tools/call", tools_call)

    StdioTransport().serve_requests(disp.handle)


if __name__ == "__main__":  # pragma: no cover
    main()

