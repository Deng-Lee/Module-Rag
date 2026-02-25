from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AssetRef:
    ref_id: str
    source_type: str
    origin_ref: str
    anchor: dict[str, Any]
    context_hint: str | None = None


@dataclass
class ParseSummary:
    pages: int | None = None
    paragraphs: int | None = None
    images: int = 0
    text_chars: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] | None = None


@dataclass
class LoaderOutput:
    md: str
    assets: list[AssetRef]
    parse_summary: ParseSummary
    doc_id: str | None = None
    version_id: str | None = None


@dataclass
class NormalizedAssets:
    ref_to_asset_id: dict[str, str]
    assets_new: int = 0
    assets_reused: int = 0
    assets_failed: int = 0


class BaseLoader(Protocol):
    def load(self, input_path: str, *, doc_id: str | None = None, version_id: str | None = None) -> LoaderOutput:
        ...


class AssetNormalizer(Protocol):
    def normalize(self, assets: list[AssetRef], *, raw_path: str, md: str) -> NormalizedAssets:
        ...
