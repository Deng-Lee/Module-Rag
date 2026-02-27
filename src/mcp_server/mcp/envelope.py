from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from ...core.response.models import ResponseIR, SourceRef
from ..jsonrpc.dispatcher import JsonRpcAppError
from ..jsonrpc.codec import INVALID_PARAMS
from .session import McpSession


def build_response_envelope(
    *,
    session: McpSession,
    tool_name: str,
    output: Any,
) -> dict[str, Any]:
    """Build MCP tools/call result envelope with L0/L1/L2 progressive enhancement.

    Contract (minimal, aligned to DEV_SPEC E-4):
    - Always return `content[0]` as a text/Markdown payload (L0 must be readable).
    - Add `structuredContent` for L1/L2 clients; strip for L0 clients.
    """
    if isinstance(output, ResponseIR):
        return _from_response_ir(session=session, tool_name=tool_name, resp=output)

    if isinstance(output, dict):
        # Tool may already return MCP-shaped {content:[...], structuredContent?:...}.
        if "content" in output:
            return _normalize_mcp_result(session=session, tool_name=tool_name, result=output)
        # Or tool may return {"text": "...", "structured": {...}}
        if "text" in output and isinstance(output.get("text"), str):
            return _from_text(
                session=session,
                tool_name=tool_name,
                text=output["text"],
                structured=output.get("structured") if isinstance(output.get("structured"), dict) else None,
            )

    if isinstance(output, str):
        return _from_text(session=session, tool_name=tool_name, text=output, structured=None)

    # Unknown output shape
    raise JsonRpcAppError(INVALID_PARAMS, f"tool returned unsupported output type: {type(output).__name__}")


def _from_text(
    *,
    session: McpSession,
    tool_name: str,
    text: str,
    structured: dict[str, Any] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}], "structuredContent": dict(structured or {})}

    _inject_common(result["structuredContent"], session=session, tool_name=tool_name)
    return degrade(session.client_level, result)


def _from_response_ir(*, session: McpSession, tool_name: str, resp: ResponseIR) -> dict[str, Any]:
    sc: dict[str, Any] = {
        "trace_id": resp.trace_id,
        "sources": [_source_to_struct(s) for s in resp.sources],
        "structured": resp.structured,
    }
    _inject_common(sc, session=session, tool_name=tool_name)

    result: dict[str, Any] = {
        "content": [{"type": "text", "text": resp.content_md}],
        "structuredContent": sc,
    }
    return degrade(session.client_level, result)


def _source_to_struct(s: SourceRef) -> dict[str, Any]:
    d = asdict(s) if is_dataclass(s) else {}
    # Drop None fields for compactness.
    return {k: v for k, v in d.items() if v is not None}


def _inject_common(sc: dict[str, Any], *, session: McpSession, tool_name: str) -> None:
    sc.setdefault("tool", tool_name)
    sc.setdefault("client_level", session.client_level)
    if session.trace_id and "trace_id" not in sc:
        sc["trace_id"] = session.trace_id


def _normalize_mcp_result(*, session: McpSession, tool_name: str, result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise JsonRpcAppError(INVALID_PARAMS, "tool result.content must be a non-empty array")
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text" or not isinstance(first.get("text"), str):
        raise JsonRpcAppError(INVALID_PARAMS, "tool result.content[0] must be a text item")

    sc = result.get("structuredContent")
    if sc is not None and not isinstance(sc, dict):
        sc = None

    sc2 = dict(sc or {})
    _inject_common(sc2, session=session, tool_name=tool_name)
    out: dict[str, Any] = {"content": content, "structuredContent": sc2}
    return degrade(session.client_level, out)

def degrade(client_level: str, result: dict[str, Any]) -> dict[str, Any]:
    """Apply L0/L1/L2 response degradation rules.

    Input `result` is allowed to be "maximal" (i.e., may include `structuredContent`).
    - L0: keep only `content` (text-first).
    - L1/L2: keep `content` + `structuredContent`.
    - Unknown: behave like L0.
    """
    out = dict(result)
    if client_level == "L0" or client_level not in {"L1", "L2"}:
        out.pop("structuredContent", None)
    _validate_mcp_tools_call_result(out)
    return out


def _validate_mcp_tools_call_result(result: dict[str, Any]) -> None:
    content = result.get("content")
    if not isinstance(content, list) or not content:
        raise JsonRpcAppError(INVALID_PARAMS, "tools/call result.content must be a non-empty array")
    first = content[0]
    if not isinstance(first, dict) or first.get("type") != "text" or not isinstance(first.get("text"), str):
        raise JsonRpcAppError(INVALID_PARAMS, "tools/call result.content[0] must be a text item")
    sc = result.get("structuredContent")
    if sc is not None and not isinstance(sc, dict):
        raise JsonRpcAppError(INVALID_PARAMS, "tools/call result.structuredContent must be an object")
