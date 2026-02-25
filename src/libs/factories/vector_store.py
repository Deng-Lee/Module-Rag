from __future__ import annotations

from typing import Any, Mapping, Tuple

from ..registry import ProviderRegistry
from .common import _create_provider


def make_vector_store(
    cfg: Mapping[str, Any], registry: ProviderRegistry
) -> Tuple[Any, Any, Any, Any]:
    vector_index = _create_provider(registry, kind="vector_index", cfg=cfg, optional=False)
    sparse_index = _create_provider(registry, kind="sparse_index", cfg=cfg, optional=True)
    retriever = _create_provider(registry, kind="retriever", cfg=cfg, optional=False)
    fusion = _create_provider(registry, kind="fusion", cfg=cfg, optional=False)
    return vector_index, sparse_index, retriever, fusion

