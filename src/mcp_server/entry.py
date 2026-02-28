from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..core.runners import IngestRunner, QueryRunner
from ..core.strategy import load_settings
from ..libs.providers import register_builtin_providers
from ..libs.registry import ProviderRegistry
from ..observability.obs import api as obs
from ..observability.readers.jsonl_reader import JsonlReader
from ..observability.sinks.jsonl import JsonlSink
from .errors import map_exception_to_jsonrpc
from .jsonrpc import Dispatcher, JsonRpcRequest, StdioTransport
from .mcp import McpProtocol, McpSession
from .mcp.tools.delete_document import DeleteDocumentToolConfig, make_tool as make_delete_tool
from .mcp.tools.get_document import GetDocumentToolConfig, make_tool as make_get_document_tool
from .mcp.tools.ingest import IngestToolConfig, make_tool as make_ingest_tool
from .mcp.tools.list_documents import ListDocumentsToolConfig, make_tool as make_list_tool
from .mcp.tools.ping import tool as ping_tool
from .mcp.tools.query import QueryToolConfig, make_tool as make_query_tool
from .mcp.tools.query_assets import QueryAssetsToolConfig, make_tool as make_query_assets_tool
from .mcp.tools.registry import ToolRegistry


@dataclass
class Runtime:
    settings_path: Path
    registry: ProviderRegistry


def build_runtime(settings_path: str | Path) -> Runtime:
    """Build provider registry snapshot (runtime wiring)."""
    registry = ProviderRegistry()
    register_builtin_providers(registry)
    return Runtime(settings_path=Path(settings_path), registry=registry)


def build_observability(settings_path: str | Path) -> tuple[JsonlSink, JsonlReader]:
    settings = load_settings(settings_path)
    sink = JsonlSink(settings.paths.logs_dir)
    reader = JsonlReader(settings.paths.logs_dir)
    obs.set_sink(sink)
    return sink, reader


def serve_stdio(settings_path: str | Path) -> None:
    _ = build_observability(settings_path)

    session = McpSession.new(client_level="L1")
    tools = ToolRegistry()

    # Core tools
    tools.register(ping_tool)
    tools.register(make_ingest_tool(runner=IngestRunner(settings_path=settings_path), cfg=IngestToolConfig(settings_path=settings_path)))
    tools.register(make_query_tool(runner=QueryRunner(settings_path=settings_path), cfg=QueryToolConfig(settings_path=settings_path)))
    tools.register(make_query_assets_tool(cfg=QueryAssetsToolConfig(settings_path=settings_path)))
    tools.register(make_get_document_tool(cfg=GetDocumentToolConfig(settings_path=settings_path)))
    tools.register(make_list_tool(cfg=ListDocumentsToolConfig(settings_path=settings_path)))
    tools.register(make_delete_tool(cfg=DeleteDocumentToolConfig(settings_path=settings_path)))

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


def main() -> None:
    settings_path = os.environ.get("MODULE_RAG_SETTINGS_PATH", "config/settings.yaml")
    serve_stdio(settings_path)


if __name__ == "__main__":  # pragma: no cover
    main()

