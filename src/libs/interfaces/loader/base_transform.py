from __future__ import annotations

from typing import Protocol


class BaseTransform(Protocol):
    def apply(self, md: str, *, ref_id_to_asset_id: dict[str, str] | None, profile_id: str) -> str:
        ...
