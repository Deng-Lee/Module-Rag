from __future__ import annotations

from typing import Any

from .jsonrpc.codec import INTERNAL_ERROR, INVALID_PARAMS
from .jsonrpc.dispatcher import JsonRpcAppError
from .jsonrpc.models import JsonRpcError


# App-specific JSON-RPC error codes (reserved server error range: -32000..-32099).
DEADLINE_EXCEEDED = -32001


def map_exception_to_jsonrpc(exc: Exception) -> JsonRpcError:
    """Map internal exceptions to a JSON-RPC error object.

    Goals (E-8):
    - Keep client-facing errors machine-readable (code/message/data).
    - Preserve JsonRpcAppError (raised intentionally by handlers/tools).
    - Provide reasonable defaults for common classes (bad args, not found, timeout, internal).
    """
    if isinstance(exc, JsonRpcAppError):
        return JsonRpcError(code=exc.code, message=exc.message, data=exc.data)

    # "Bad args" bucket: treat as invalid params.
    if isinstance(exc, (TypeError, ValueError)):
        return JsonRpcError(code=INVALID_PARAMS, message="invalid params", data={"exc_type": type(exc).__name__})

    # "Not found" bucket: still invalid params from JSON-RPC POV (caller provides wrong identifier/path).
    if isinstance(exc, FileNotFoundError):
        return JsonRpcError(code=INVALID_PARAMS, message="not found", data={"exc_type": type(exc).__name__})

    # Timeout bucket.
    if isinstance(exc, TimeoutError):
        return JsonRpcError(code=DEADLINE_EXCEEDED, message="deadline exceeded", data={"exc_type": type(exc).__name__})

    # Default: internal error.
    return JsonRpcError(code=INTERNAL_ERROR, message="internal error", data={"exc_type": type(exc).__name__})


def attach_trace_id(data: Any | None, trace_id: str | None) -> Any | None:
    """Best-effort inject `trace_id` into JSON-RPC error data."""
    if not trace_id:
        return data
    if data is None:
        return {"trace_id": trace_id}
    if isinstance(data, dict) and "trace_id" not in data:
        out = dict(data)
        out["trace_id"] = trace_id
        return out
    return data

