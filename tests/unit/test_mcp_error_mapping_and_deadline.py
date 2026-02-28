from __future__ import annotations

import time

import pytest

from src.mcp_server.errors import DEADLINE_EXCEEDED, map_exception_to_jsonrpc
from src.mcp_server.jsonrpc.codec import INTERNAL_ERROR, INVALID_PARAMS
from src.mcp_server.jsonrpc.dispatcher import JsonRpcAppError
from src.mcp_server.mcp.protocol import McpProtocol
from src.mcp_server.mcp.session import McpSession
from src.mcp_server.mcp.tools.ping import tool as ping_tool
from src.mcp_server.mcp.tools.registry import ToolRegistry


def test_map_exception_to_jsonrpc_common_buckets() -> None:
    e1 = JsonRpcAppError(INVALID_PARAMS, "bad", {"x": 1})
    err1 = map_exception_to_jsonrpc(e1)
    assert err1.code == INVALID_PARAMS and err1.message == "bad" and err1.data == {"x": 1}

    err2 = map_exception_to_jsonrpc(ValueError("x"))
    assert err2.code == INVALID_PARAMS

    err3 = map_exception_to_jsonrpc(FileNotFoundError("missing"))
    assert err3.code == INVALID_PARAMS and err3.message == "not found"

    err4 = map_exception_to_jsonrpc(TimeoutError("t"))
    assert err4.code == DEADLINE_EXCEEDED

    err5 = map_exception_to_jsonrpc(RuntimeError("boom"))
    assert err5.code == INTERNAL_ERROR


def test_session_with_deadline_sets_deadline_ts(mock_clock: float) -> None:
    _ = mock_clock
    s = McpSession.new("L1")
    s2 = s.with_deadline(1500)
    assert s2.deadline_ts is not None
    assert abs(s2.deadline_ts - (time.time() + 1.5)) < 1e-6


def test_protocol_deadline_exceeded_is_structured_error(mock_clock: float) -> None:
    _ = mock_clock
    reg = ToolRegistry()
    reg.register(ping_tool)
    proto = McpProtocol(tools=reg)

    s = McpSession.new("L1").with_deadline(0)
    with pytest.raises(JsonRpcAppError) as ei:
        proto.handle_tools_call(s, name="library.ping", args={"message": "hi"})
    assert ei.value.code == DEADLINE_EXCEEDED
    assert isinstance(ei.value.data, dict) and "trace_id" in ei.value.data

