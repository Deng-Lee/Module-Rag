from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from ..session import McpSession


ToolHandler = Callable[[McpSession, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


class Tool(Protocol):
    spec: ToolSpec

    def call(self, session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        ...


@dataclass
class FunctionTool:
    spec: ToolSpec
    fn: ToolHandler

    def call(self, session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        return self.fn(session, args)

