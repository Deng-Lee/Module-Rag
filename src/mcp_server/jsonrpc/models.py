from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class JsonRpcRequest:
    jsonrpc: str
    method: str
    params: Any | None
    id: Any | None  # JSON-RPC allows string|number|null; keep as Any


@dataclass(frozen=True)
class JsonRpcError:
    code: int
    message: str
    data: Any | None = None

    def to_dict(self) -> JsonDict:
        d: JsonDict = {"code": int(self.code), "message": str(self.message)}
        if self.data is not None:
            d["data"] = self.data
        return d


@dataclass(frozen=True)
class JsonRpcResponse:
    jsonrpc: str = "2.0"
    id: Any | None = None
    result: Any | None = None
    error: JsonRpcError | None = None

    def to_dict(self) -> JsonDict:
        d: JsonDict = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["result"] = self.result
        return d

