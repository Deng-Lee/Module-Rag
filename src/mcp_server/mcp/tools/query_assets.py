from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ....core.strategy import load_settings
from ....ingestion.stages.storage.sqlite import SqliteStore
from ...jsonrpc.codec import INVALID_PARAMS
from ...jsonrpc.dispatcher import JsonRpcAppError
from ..session import McpSession
from .base import FunctionTool, ToolSpec


@dataclass
class QueryAssetsToolConfig:
    settings_path: str | Path = "config/settings.yaml"
    default_variant: str = "thumb"  # thumb|raw
    default_max_bytes: int = 256 * 1024
    hard_max_bytes: int = 2 * 1024 * 1024


def _guess_mime(path: Path) -> str:
    mt, _ = mimetypes.guess_type(path.name)
    return mt or "application/octet-stream"


def _find_asset_path(assets_dir: Path, rel_path: str | None, asset_id: str) -> Path | None:
    if rel_path:
        p = (assets_dir / rel_path).resolve()
        if p.exists() and p.is_file():
            return p
    matches = list(assets_dir.glob(f"{asset_id}.*"))
    if matches:
        return matches[0]
    return None


def _read_bytes_limited(p: Path, *, max_bytes: int) -> bytes:
    data = p.read_bytes()
    if max_bytes > 0 and len(data) > max_bytes:
        raise ValueError("asset_too_large")
    return data


def make_tool(*, cfg: QueryAssetsToolConfig | None = None) -> FunctionTool:
    cfg = cfg or QueryAssetsToolConfig()

    def _handler(session: McpSession, args: dict[str, Any]) -> dict[str, Any]:
        _ = session
        asset_ids = args.get("asset_ids")
        if not isinstance(asset_ids, list) or not asset_ids or not all(isinstance(x, str) and x for x in asset_ids):
            raise JsonRpcAppError(INVALID_PARAMS, "missing required param: asset_ids (non-empty string array)")

        variant = args.get("variant", cfg.default_variant)
        if not isinstance(variant, str) or variant not in {"thumb", "raw"}:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: variant must be thumb|raw")

        max_bytes = args.get("max_bytes", cfg.default_max_bytes)
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_bytes must be integer")
        if max_bytes < 1:
            raise JsonRpcAppError(INVALID_PARAMS, "invalid param: max_bytes must be positive")
        if max_bytes > cfg.hard_max_bytes:
            max_bytes = cfg.hard_max_bytes

        settings = load_settings(cfg.settings_path)
        assets_dir = settings.paths.assets_dir
        sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")

        # Resolve rel paths via SQLite assets table (best-effort).
        rel_by_id = sqlite.fetch_assets(asset_ids)

        found: list[dict[str, Any]] = []
        missing: list[str] = []
        too_large: list[str] = []

        for aid in asset_ids:
            p = _find_asset_path(assets_dir, rel_by_id.get(aid), aid)
            if p is None:
                missing.append(aid)
                continue

            try:
                data = _read_bytes_limited(p, max_bytes=max_bytes)
            except Exception:
                too_large.append(aid)
                continue

            mime = _guess_mime(p)

            # NOTE: We currently do not generate real thumbnails (dependency-free).
            # `thumb` behaves as a "bounded raw" variant. This preserves the E-7
            # contract while keeping the implementation light.
            b64 = base64.b64encode(data).decode("ascii")
            found.append(
                {
                    "asset_id": aid,
                    "mime": mime,
                    "variant": variant,
                    "size_bytes": len(data),
                    "bytes_b64": b64,
                }
            )

        text_lines = [
            "Assets fetched.",
            f"- requested: {len(asset_ids)}",
            f"- returned: {len(found)}",
            f"- missing: {len(missing)}",
            f"- too_large: {len(too_large)} (max_bytes={max_bytes})",
        ]
        return {
            "text": "\n".join(text_lines),
            "structured": {
                "variant": variant,
                "max_bytes": max_bytes,
                "assets": found,
                "missing": missing,
                "too_large": too_large,
            },
        }

    return FunctionTool(
        spec=ToolSpec(
            name="library.query_assets",
            description="Batch fetch asset bytes (default: thumb) using asset_id anchors.",
            input_schema={
                "type": "object",
                "properties": {
                    "asset_ids": {"type": "array"},
                    "variant": {"type": "string"},
                    "max_bytes": {"type": "integer"},
                },
                "required": ["asset_ids"],
                "additionalProperties": False,
            },
        ),
        fn=_handler,
    )

