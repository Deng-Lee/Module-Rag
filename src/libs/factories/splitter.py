from __future__ import annotations

from typing import Any, Mapping, Tuple

from ..registry import ProviderRegistry
from .common import _create_provider


def make_splitter(cfg: Mapping[str, Any], registry: ProviderRegistry) -> Tuple[Any, Any]:
    sectioner = _create_provider(registry, kind="sectioner", cfg=cfg, optional=False)
    chunker = _create_provider(registry, kind="chunker", cfg=cfg, optional=False)
    return sectioner, chunker

