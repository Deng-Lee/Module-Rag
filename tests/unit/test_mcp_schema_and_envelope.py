from __future__ import annotations

import pytest

from src.core.response.models import ResponseIR
from src.mcp_server.jsonrpc.dispatcher import JsonRpcAppError
from src.mcp_server.mcp.envelope import build_response_envelope
from src.mcp_server.mcp.schema import SchemaValidationError, validate_tool_args
from src.mcp_server.mcp.session import McpSession


def test_validate_tool_args_ok_and_additional_properties() -> None:
    schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "additionalProperties": False,
    }
    assert validate_tool_args(schema, {"message": "hi"}) == {"message": "hi"}
    with pytest.raises(SchemaValidationError):
        validate_tool_args(schema, {"message": "hi", "x": 1})


def test_build_response_envelope_l0_vs_l1() -> None:
    resp = ResponseIR(trace_id="t1", content_md="hello", sources=[], structured={"x": 1})

    l0 = build_response_envelope(session=McpSession.new("L0"), tool_name="t", output=resp)
    assert "content" in l0 and "structuredContent" not in l0

    l1 = build_response_envelope(session=McpSession.new("L1"), tool_name="t", output=resp)
    assert "content" in l1 and "structuredContent" in l1
    assert l1["structuredContent"]["trace_id"] == "t1"


def test_build_response_envelope_rejects_bad_shape() -> None:
    with pytest.raises(JsonRpcAppError):
        build_response_envelope(session=McpSession.new("L0"), tool_name="t", output=object())

