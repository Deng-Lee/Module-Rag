from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RetrievalViewConfig:
    """Config for building `chunk_retrieval_text` (retrieval view)."""

    template_id: str = "facts_only"
    include_heading_text: bool = False


def build_chunk_retrieval_text(
    chunk_text: str,
    *,
    template_id: str,
    enrichments: dict[str, Any] | None = None,
    heading_text: str | None = None,
) -> str:
    """Build the retrieval view.

    - `chunk_text` is the facts layer (must remain unchanged elsewhere).
    - `enrichments` contains optional snippets like caption/ocr/keywords.
    - The output is used for sparse/dense encoding, not for citations.
    """

    enrichments = dict(enrichments or {})

    # Always start from facts.
    parts: list[str] = [chunk_text.strip("\n")]

    if template_id == "facts_only":
        return parts[0]

    if template_id not in {"facts_plus_enrich", "facts_plus_enrich_v1"}:
        raise ValueError(f"unknown template_id: {template_id}")

    if heading_text:
        parts.append(f"[heading] {heading_text.strip()}")

    # Stable order for deterministic output.
    for key in sorted(enrichments.keys()):
        value = enrichments.get(key)
        if value is None:
            continue

        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(f"[{key}] {text}")
            continue

        if isinstance(value, list):
            for item in value:
                if not isinstance(item, str):
                    continue
                text = item.strip()
                if text:
                    parts.append(f"[{key}] {text}")
            continue

    return "\n\n".join(p for p in parts if p)
