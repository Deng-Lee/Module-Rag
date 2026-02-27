from __future__ import annotations

import json
from typing import Any

from .models import JsonRpcError, JsonRpcRequest, JsonRpcResponse


# JSON-RPC 2.0 standard error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcCodecError(ValueError):
    def __init__(self, code: int, message: str, *, req_id: Any | None = None, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.req_id = req_id
        self.data = data


def decode_request(line: str) -> JsonRpcRequest:
    """
    Decode one JSON-RPC request from a line-delimited JSON string.
    """
    try:
        raw = json.loads(line)
    except Exception as e:
        raise JsonRpcCodecError(PARSE_ERROR, "parse error", data=str(e)) from e

    if not isinstance(raw, dict):
        raise JsonRpcCodecError(INVALID_REQUEST, "invalid request: root must be object")

    jsonrpc = raw.get("jsonrpc")
    if jsonrpc != "2.0":
        raise JsonRpcCodecError(INVALID_REQUEST, "invalid request: jsonrpc must be '2.0'", req_id=raw.get("id"))

    method = raw.get("method")
    if not isinstance(method, str) or not method:
        raise JsonRpcCodecError(INVALID_REQUEST, "invalid request: method must be non-empty string", req_id=raw.get("id"))

    params = raw.get("params") if "params" in raw else None
    req_id = raw.get("id") if "id" in raw else None
    return JsonRpcRequest(jsonrpc="2.0", method=method, params=params, id=req_id)


def encode_response(resp: JsonRpcResponse) -> str:
    return json.dumps(resp.to_dict(), ensure_ascii=False, separators=(",", ":"))


def encode_error(req_id: Any | None, code: int, message: str, data: Any | None = None) -> str:
    resp = JsonRpcResponse(id=req_id, error=JsonRpcError(code=code, message=message, data=data))
    return encode_response(resp)

