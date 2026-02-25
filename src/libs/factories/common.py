from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from ..registry import ProviderNotFoundError, ProviderRegistry


@dataclass
class NoopProvider:
    kind: str
    provider_id: str = "noop"

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"NoopProvider(kind={self.kind!r})"


def _extract_provider_cfg(cfg: Mapping[str, Any], kind: str) -> Dict[str, Any] | None:
    # Preferred shape: cfg["providers"][kind] = {provider_id, params}
    providers = cfg.get("providers")
    if isinstance(providers, Mapping) and kind in providers:
        value = providers[kind]
    elif kind in cfg:
        value = cfg[kind]
    elif f"{kind}_provider" in cfg:
        value = cfg[f"{kind}_provider"]
    else:
        return None

    if isinstance(value, str):
        return {"provider_id": value, "params": {}}
    if isinstance(value, Mapping):
        provider_id = value.get("provider_id") or value.get("id")
        params = value.get("params")
        if params is None:
            params = {k: v for k, v in value.items() if k not in {"provider_id", "id"}}
        return {"provider_id": provider_id, "params": dict(params)}
    raise TypeError(f"invalid provider config for kind={kind!r}")


def _create_provider(
    registry: ProviderRegistry,
    *,
    kind: str,
    cfg: Mapping[str, Any],
    optional: bool = False,
) -> Any:
    provider_cfg = _extract_provider_cfg(cfg, kind)
    if provider_cfg is None:
        if optional:
            return NoopProvider(kind)
        raise ValueError(f"missing provider config for kind={kind}")

    provider_id = provider_cfg.get("provider_id")
    if not provider_id:
        if optional:
            return NoopProvider(kind)
        raise ValueError(f"missing provider_id for kind={kind}")

    if provider_id == "noop" and optional:
        if registry.has(kind, provider_id):
            return registry.create(kind, provider_id)
        return NoopProvider(kind)

    try:
        return registry.create(kind, provider_id, **provider_cfg.get("params", {}))
    except ProviderNotFoundError:
        raise

