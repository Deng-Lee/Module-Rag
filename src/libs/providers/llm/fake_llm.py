from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...interfaces.llm import LLMResult


@dataclass
class FakeLLM:
    """Deterministic LLM stub for tests and local runs."""

    name: str = "fake-llm"

    def generate(self, mode: str, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResult:
        content = _last_text_content(messages)
        text = f"[{self.name}:{mode}] {content}".strip()
        return LLMResult(
            text=text,
            tokens_in=len(content) if content else 0,
            tokens_out=len(text),
            meta={"provider": self.name, "mode": mode},
        )


def _last_text_content(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return ""
    last = messages[-1]
    content = last.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(p for p in parts if p)
    return ""
