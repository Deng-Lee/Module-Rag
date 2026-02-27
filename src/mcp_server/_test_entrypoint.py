from __future__ import annotations

from .jsonrpc.dispatcher import Dispatcher
from .jsonrpc.models import JsonRpcRequest
from .jsonrpc.stdio_transport import StdioTransport


def main() -> None:
    disp = Dispatcher()

    def ping(req: JsonRpcRequest):
        return {"ok": True, "params": req.params}

    disp.register("ping", ping)

    StdioTransport().serve_requests(disp.handle)


if __name__ == "__main__":  # pragma: no cover
    main()
