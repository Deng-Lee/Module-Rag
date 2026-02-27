from __future__ import annotations

from .jsonrpc.stdio_transport import StdioTransport


def main() -> None:
    def handler(method, params, req_id):
        _ = req_id
        if method == "ping":
            return {"ok": True, "params": params}
        raise RuntimeError(f"unknown method: {method}")

    StdioTransport().serve(handler)


if __name__ == "__main__":  # pragma: no cover
    main()

