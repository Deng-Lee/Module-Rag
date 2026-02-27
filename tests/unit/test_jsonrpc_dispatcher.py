from __future__ import annotations

from src.mcp_server.jsonrpc.codec import INVALID_PARAMS, METHOD_NOT_FOUND
from src.mcp_server.jsonrpc.dispatcher import Dispatcher, JsonRpcAppError
from src.mcp_server.jsonrpc.models import JsonRpcRequest


def test_dispatcher_method_not_found() -> None:
    d = Dispatcher()
    resp = d.handle(JsonRpcRequest(jsonrpc="2.0", method="nope", params=None, id=1))
    assert resp.error is not None
    assert resp.error.code == METHOD_NOT_FOUND


def test_dispatcher_routes_and_returns_result() -> None:
    d = Dispatcher()

    def ping(req: JsonRpcRequest):
        return {"ok": True, "method": req.method}

    d.register("ping", ping)
    resp = d.handle(JsonRpcRequest(jsonrpc="2.0", method="ping", params=None, id=1))
    assert resp.error is None
    assert resp.result == {"ok": True, "method": "ping"}


def test_dispatcher_exception_maps_to_internal_error() -> None:
    d = Dispatcher()

    def bad(req: JsonRpcRequest):
        raise RuntimeError("boom")

    d.register("bad", bad)
    resp = d.handle(JsonRpcRequest(jsonrpc="2.0", method="bad", params=None, id=1))
    assert resp.error is not None
    assert resp.error.code == -32603


def test_dispatcher_app_error_uses_custom_code() -> None:
    d = Dispatcher()

    def bad_params(req: JsonRpcRequest):
        raise JsonRpcAppError(INVALID_PARAMS, "invalid params", {"x": 1})

    d.register("bad_params", bad_params)
    resp = d.handle(JsonRpcRequest(jsonrpc="2.0", method="bad_params", params=None, id=1))
    assert resp.error is not None
    assert resp.error.code == INVALID_PARAMS
    assert resp.error.message == "invalid params"
    assert resp.error.data == {"x": 1}
