from __future__ import annotations

import json

import pytest

from src.mcp_server.jsonrpc.codec import INVALID_REQUEST, PARSE_ERROR, JsonRpcCodecError, decode_request, encode_error


def test_decode_request_ok() -> None:
    req = decode_request('{"jsonrpc":"2.0","id":1,"method":"ping","params":{"a":1}}')
    assert req.id == 1
    assert req.method == "ping"
    assert req.params == {"a": 1}


def test_decode_request_parse_error() -> None:
    with pytest.raises(JsonRpcCodecError) as e:
        decode_request("{not json")
    assert e.value.code == PARSE_ERROR


def test_decode_request_invalid_request() -> None:
    with pytest.raises(JsonRpcCodecError) as e:
        decode_request('{"jsonrpc":"2.0","id":1,"params":{}}')
    assert e.value.code == INVALID_REQUEST


def test_encode_error_shape() -> None:
    s = encode_error(1, -32000, "bad", {"x": 1})
    obj = json.loads(s)
    assert obj["jsonrpc"] == "2.0"
    assert obj["id"] == 1
    assert obj["error"]["code"] == -32000
    assert obj["error"]["message"] == "bad"
    assert obj["error"]["data"] == {"x": 1}

