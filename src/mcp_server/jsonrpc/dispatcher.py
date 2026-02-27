from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .codec import INTERNAL_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND
from .models import JsonRpcError, JsonRpcRequest, JsonRpcResponse


Handler = Callable[[JsonRpcRequest], Any]


@dataclass
class Dispatcher:
    """JSON-RPC method dispatcher (thin routing layer)."""

    _handlers: dict[str, Handler] = field(default_factory=dict)
    error_mapper: Callable[[Exception], JsonRpcError] | None = None

    def register(self, method: str, handler: Handler) -> None:
        if not isinstance(method, str) or not method:
            raise ValueError("method must be non-empty string")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers[method] = handler

    def handle(self, req: JsonRpcRequest) -> JsonRpcResponse:
        if req.jsonrpc != "2.0" or not req.method:
            return JsonRpcResponse(id=req.id, error=JsonRpcError(INVALID_REQUEST, "invalid request"))

        handler = self._handlers.get(req.method)
        if handler is None:
            return JsonRpcResponse(id=req.id, error=JsonRpcError(METHOD_NOT_FOUND, "method not found"))

        try:
            result = handler(req)
            # Notification support: if id is None, return an empty response object (transport may drop it).
            return JsonRpcResponse(id=req.id, result=result)
        except Exception as e:
            mapper = self.error_mapper or default_error_mapper
            err = mapper(e)
            return JsonRpcResponse(id=req.id, error=err)


def default_error_mapper(exc: Exception) -> JsonRpcError:
    # Keep it conservative: leak minimal info; verbose details should go to trace/logs.
    return JsonRpcError(code=INTERNAL_ERROR, message="internal error", data={"exc_type": type(exc).__name__})

