from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class LLMResult:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


class LLM(Protocol):
    def generate(self, mode: str, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResult:
        ...
