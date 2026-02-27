from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Callable, TextIO

from .codec import INTERNAL_ERROR, JsonRpcCodecError, decode_request, encode_error, encode_response
from .models import JsonRpcResponse


Handler = Callable[[str, Any | None, Any | None], Any]
RequestHandler = Callable[[Any], JsonRpcResponse]


@dataclass
class StdioTransport:
    """Line-delimited JSON-RPC 2.0 transport over stdio."""

    stdin: TextIO = sys.stdin
    stdout: TextIO = sys.stdout

    def serve(self, handler: Handler) -> None:
        """
        Read requests from stdin until EOF, dispatch to handler, and write responses to stdout.

        - Notification (id is None): do not write a response.
        - Any decode errors are returned as JSON-RPC error responses when possible.
        """
        for line in self._iter_lines():
            line = line.strip()
            if not line:
                continue

            try:
                req = decode_request(line)
            except JsonRpcCodecError as e:
                self._write(encode_error(e.req_id, e.code, e.message, e.data))
                continue
            except Exception as e:
                self._write(encode_error(None, INTERNAL_ERROR, "internal error", str(e)))
                continue

            if req.id is None:
                # Notification: execute but do not respond.
                try:
                    handler(req.method, req.params, req.id)
                except Exception:
                    pass
                continue

            try:
                result = handler(req.method, req.params, req.id)
                resp = JsonRpcResponse(id=req.id, result=result)
                self._write(encode_response(resp))
            except Exception as e:
                self._write(encode_error(req.id, INTERNAL_ERROR, "internal error", str(e)))

    def serve_requests(self, handler: RequestHandler) -> None:
        """Serve using a request-aware handler (Dispatcher-compatible)."""
        for line in self._iter_lines():
            line = line.strip()
            if not line:
                continue
            try:
                req = decode_request(line)
            except JsonRpcCodecError as e:
                self._write(encode_error(e.req_id, e.code, e.message, e.data))
                continue
            except Exception as e:
                self._write(encode_error(None, INTERNAL_ERROR, "internal error", str(e)))
                continue

            resp = handler(req)
            if req.id is None:
                # Notification: do not emit a response.
                continue
            self._write(encode_response(resp))

    def _iter_lines(self):
        while True:
            line = self.stdin.readline()
            if line == "":
                break
            yield line

    def _write(self, payload: str) -> None:
        self.stdout.write(payload + "\n")
        self.stdout.flush()
