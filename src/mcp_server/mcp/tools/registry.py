from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import Tool


@dataclass
class ToolRegistry:
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        name = getattr(tool, "spec").name
        if not isinstance(name, str) or not name:
            raise ValueError("tool name must be non-empty string")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_specs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for tool in self._tools.values():
            spec = tool.spec
            out.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "inputSchema": spec.input_schema,
                }
            )
        out.sort(key=lambda x: x["name"])
        return out

