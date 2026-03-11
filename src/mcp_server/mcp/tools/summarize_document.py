from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.strategy import load_settings
from ...jsonrpc.codec import INTERNAL_ERROR, INVALID_PARAMS
from ...jsonrpc.dispatcher import JsonRpcAppError
from ..session import McpSession
from .base import FunctionTool, ToolSpec


@dataclass
class SummarizeDocumentToolConfig:
    settings_path: str | Path = "config/settings.yaml"
    default_max_chars: int = 600
    hard_max_chars: int = 4_000
    default_max_segments: int = 3
    hard_max_segments: int = 8


def _resolve_md_norm_path(*, settings_path: str | Path, doc_id: str, version_id: str) -> Path:
    settings = load_settings(settings_path)
    return (settings.paths.md_dir / doc_id / version_id / "md_norm.md").resolve()


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _clean_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    if text.startswith("```"):
        return ""
    if re.match(r"^!\[[^\]]*\]\([^)]+\)$", text):
        return ""
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"^[-*+]\s+", "", text)
    text = re.sub(r"^\d+\.\s+", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_summary(md_text: str, *, max_chars: int, max_segments: int) -> tuple[str, list[str]]:
    warnings: list[str] = []
    segments: list[str] = []
    in_code_block = False

    for raw_line in md_text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        cleaned = _clean_line(raw_line)
        if not cleaned:
            continue
        segments.append(cleaned)

    picked: list[str] = []
    total_chars = 0
    for segment in segments:
        if len(picked) >= max_segments:
            warnings.append("segment_limit_applied")
            break
        candidate_len = total_chars + len(segment) + (1 if picked else 0)
        if candidate_len > max_chars:
            remain = max_chars - total_chars - (1 if picked else 0)
            if remain > 40:
                picked.append(segment[:remain].rstrip())
                warnings.append("summary_truncated")
            elif not picked:
                picked.append(segment[:max_chars].rstrip())
                warnings.append("summary_truncated")
            else:
                warnings.append("summary_truncated")
            break
        picked.append(segment)
        total_chars = candidate_len

    if not picked:
        picked = [md_text[: max(1, min(len(md_text), max_chars))].strip()]
        warnings.append("summary_fallback_used")

    summary = "\n".join(f"- {segment}" for segment in picked if segment)
    return summary, list(dict.fromkeys(warnings))


def make_tool(*, cfg: SummarizeDocumentToolConfig | None = None) -> FunctionTool:
    cfg = cfg or SummarizeDocumentToolConfig()

    def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        _ = session
        doc_id = args.get("doc_id")
        version_id = args.get("version_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise JsonRpcAppError(INVALID_PARAMS, "missing required param: doc_id")
        if not isinstance(version_id, str) or not version_id:
            raise JsonRpcAppError(INVALID_PARAMS, "missing required param: version_id")

        max_chars = args.get("max_chars", cfg.default_max_chars)
        if isinstance(max_chars, bool) or not isinstance(max_chars, int):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_chars must be integer")
        if max_chars < 1:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_chars must be positive")
        if max_chars > cfg.hard_max_chars:
            max_chars = cfg.hard_max_chars

        max_segments = args.get("max_segments", cfg.default_max_segments)
        if isinstance(max_segments, bool) or not isinstance(max_segments, int):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_segments must be integer")
        if max_segments < 1:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_segments must be positive")
        if max_segments > cfg.hard_max_segments:
            max_segments = cfg.hard_max_segments

        md_path = _resolve_md_norm_path(
            settings_path=cfg.settings_path, doc_id=doc_id, version_id=version_id
        )
        if not md_path.exists():
            raise JsonRpcAppError(
                INVALID_PARAMS,
                "document not found",
                {"doc_id": doc_id, "version_id": version_id},
            )

        try:
            md_text = _read_text(md_path)
            summary_text, warnings = _build_summary(
                md_text, max_chars=max_chars, max_segments=max_segments
            )
        except JsonRpcAppError:
            raise
        except Exception as e:
            raise JsonRpcAppError(
                INTERNAL_ERROR, "failed to summarize document", {"exc_type": type(e).__name__}
            ) from e

        return {
            "text": summary_text,
            "structured": {
                "doc_id": doc_id,
                "version_id": version_id,
                "warnings": warnings,
                "max_chars": max_chars,
                "max_segments": max_segments,
                "summary_char_count": len(summary_text),
            },
        }

    return FunctionTool(
        spec=ToolSpec(
            name="library_summarize_document",
            description="Return a concise extractive summary for a doc_id/version_id.",
            input_schema={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "version_id": {"type": "string"},
                    "max_chars": {"type": "integer"},
                    "max_segments": {"type": "integer"},
                },
                "required": ["doc_id", "version_id"],
                "additionalProperties": False,
            },
        ),
        fn=_handler,
    )
