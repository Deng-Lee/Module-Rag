from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict


class ProviderRegistryError(RuntimeError):
    pass


class ProviderAlreadyRegisteredError(ProviderRegistryError):
    pass


class ProviderNotFoundError(ProviderRegistryError):
    pass


@dataclass
class ProviderRegistry:
    _registry: Dict[str, Dict[str, Callable[..., Any]]]

    def __init__(self) -> None:
        self._registry = {}

    def register(self, kind: str, provider_id: str, ctor: Callable[..., Any]) -> None:
        if not isinstance(kind, str) or not kind:
            raise ValueError("kind must be a non-empty string")
        if not isinstance(provider_id, str) or not provider_id:
            raise ValueError("provider_id must be a non-empty string")
        if not callable(ctor):
            raise TypeError("ctor must be callable")

        by_kind = self._registry.setdefault(kind, {})
        if provider_id in by_kind:
            raise ProviderAlreadyRegisteredError(f"{kind}:{provider_id} already registered")
        by_kind[provider_id] = ctor

    def has(self, kind: str, provider_id: str) -> bool:
        return kind in self._registry and provider_id in self._registry[kind]

    def get(self, kind: str, provider_id: str) -> Callable[..., Any]:
        try:
            return self._registry[kind][provider_id]
        except KeyError as exc:
            raise ProviderNotFoundError(f"{kind}:{provider_id} not found") from exc

    def create(self, kind: str, provider_id: str, **kwargs: Any) -> Any:
        ctor = self.get(kind, provider_id)
        return ctor(**kwargs)

