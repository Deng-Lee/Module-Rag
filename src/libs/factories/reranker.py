from __future__ import annotations

from typing import Any, Mapping

from ..registry import ProviderRegistry
from .common import _create_provider


def make_reranker(cfg: Mapping[str, Any], registry: ProviderRegistry) -> Any:
    return _create_provider(registry, kind="reranker", cfg=cfg, optional=True)

