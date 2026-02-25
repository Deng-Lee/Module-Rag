from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AssetStore:
    assets_dir: Path

    def __post_init__(self) -> None:
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def write_bytes(self, data: bytes, suffix: str | None = None) -> tuple[str, Path, bool]:
        asset_id = hashlib.sha256(data).hexdigest()
        suffix = _normalize_suffix(suffix)
        path = self.assets_dir / f"{asset_id}{suffix}"

        if path.exists():
            return asset_id, path, True

        path.write_bytes(data)
        return asset_id, path, False


def _normalize_suffix(suffix: str | None) -> str:
    if not suffix:
        return ".bin"
    if not suffix.startswith("."):
        return f".{suffix}"
    return suffix
