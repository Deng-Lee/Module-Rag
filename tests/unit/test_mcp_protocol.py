from __future__ import annotations

import pytest

from src.mcp_server.jsonrpc.dispatcher import JsonRpcAppError
from src.mcp_server.mcp.protocol import McpProtocol
from src.mcp_server.mcp.session import McpSession
from src.mcp_server.mcp.tools.ping import tool as ping_tool
from src.mcp_server.mcp.tools.registry import ToolRegistry


def test_mcp_tools_list_and_call() -> None:
    reg = ToolRegistry()
    reg.register(ping_tool)
    proto = McpProtocol(tools=reg)
    sess = McpSession.new("L0")

    lst = proto.handle_tools_list(sess)
    assert "tools" in lst
    names = [t["name"] for t in lst["tools"]]
    assert "library.ping" in names

    out = proto.handle_tools_call(sess, name="library.ping", args={"message": "hi"})
    assert out["content"][0]["type"] == "text"
    assert "hi" in out["content"][0]["text"]


def test_mcp_tools_call_unknown_tool_is_invalid_params() -> None:
    reg = ToolRegistry()
    proto = McpProtocol(tools=reg)
    sess = McpSession.new("L0")
    with pytest.raises(JsonRpcAppError) as e:
        proto.handle_tools_call(sess, name="nope", args={})
    assert e.value.code == -32602

