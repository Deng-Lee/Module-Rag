from __future__ import annotations

from typing import Any, Mapping

from ..registry import ProviderRegistry
from .common import _create_provider


def make_llm(cfg: Mapping[str, Any], registry: ProviderRegistry) -> Any:
    return _create_provider(registry, kind="llm", cfg=cfg, optional=False)

