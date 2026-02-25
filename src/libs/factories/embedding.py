from __future__ import annotations

from typing import Any, Mapping, Tuple

from ..registry import ProviderRegistry
from .common import _create_provider


def make_embedding(cfg: Mapping[str, Any], registry: ProviderRegistry) -> Tuple[Any, Any]:
    embedder = _create_provider(registry, kind="embedder", cfg=cfg, optional=False)
    sparse_encoder = _create_provider(registry, kind="sparse_encoder", cfg=cfg, optional=True)
    return embedder, sparse_encoder

