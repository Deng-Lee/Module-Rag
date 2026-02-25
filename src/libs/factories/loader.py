from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..registry import ProviderRegistry
from .common import _create_provider


@dataclass
class LoaderGraph:
    loader: Any
    asset_normalizer: Any


def make_loader_components(cfg: Mapping[str, Any], registry: ProviderRegistry) -> LoaderGraph:
    loader = _create_provider(registry, kind="loader", cfg=cfg, optional=False)
    asset_normalizer = _create_provider(registry, kind="asset_normalizer", cfg=cfg, optional=True)
    return LoaderGraph(loader=loader, asset_normalizer=asset_normalizer)

