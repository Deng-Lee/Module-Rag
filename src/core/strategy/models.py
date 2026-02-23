from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


def _as_path(v: Any, default: Path) -> Path:
    if v is None:
        return default
    if isinstance(v, Path):
        return v
    if isinstance(v, str):
        return Path(v)
    raise TypeError(f"expected path-like value, got {type(v).__name__}")


def _as_int(v: Any, default: int) -> int:
    if v is None:
        return default
    if isinstance(v, bool):
        raise TypeError("expected int, got bool")
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    raise TypeError(f"expected int-like value, got {type(v).__name__}")


@dataclass
class PathsSettings:
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    md_dir: Path = Path("data/md")
    assets_dir: Path = Path("data/assets")
    chroma_dir: Path = Path("data/chroma")
    sqlite_dir: Path = Path("data/sqlite")
    cache_dir: Path = Path("cache")
    logs_dir: Path = Path("logs")

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "PathsSettings":
        d = d or {}
        return cls(
            data_dir=_as_path(d.get("data_dir"), cls.data_dir),
            raw_dir=_as_path(d.get("raw_dir"), cls.raw_dir),
            md_dir=_as_path(d.get("md_dir"), cls.md_dir),
            assets_dir=_as_path(d.get("assets_dir"), cls.assets_dir),
            chroma_dir=_as_path(d.get("chroma_dir"), cls.chroma_dir),
            sqlite_dir=_as_path(d.get("sqlite_dir"), cls.sqlite_dir),
            cache_dir=_as_path(d.get("cache_dir"), cls.cache_dir),
            logs_dir=_as_path(d.get("logs_dir"), cls.logs_dir),
        )


@dataclass
class ServerSettings:
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 7860

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "ServerSettings":
        d = d or {}
        host = d.get("dashboard_host", cls.dashboard_host)
        if not isinstance(host, str):
            raise TypeError(f"dashboard_host must be str, got {type(host).__name__}")
        return cls(
            dashboard_host=host,
            dashboard_port=_as_int(d.get("dashboard_port"), cls.dashboard_port),
        )


@dataclass
class DefaultsSettings:
    strategy_config_id: str = "local.default"

    @classmethod
    def from_dict(cls, d: Mapping[str, Any] | None) -> "DefaultsSettings":
        d = d or {}
        v = d.get("strategy_config_id", cls.strategy_config_id)
        if not isinstance(v, str):
            raise TypeError(f"strategy_config_id must be str, got {type(v).__name__}")
        return cls(strategy_config_id=v)


@dataclass
class Settings:
    paths: PathsSettings = field(default_factory=PathsSettings)
    server: ServerSettings = field(default_factory=ServerSettings)
    defaults: DefaultsSettings = field(default_factory=DefaultsSettings)

    # Keep the raw mapping for debugging; must be JSON-serializable.
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> "Settings":
        raw = dict(raw or {})
        paths = raw.get("paths")
        server = raw.get("server")
        defaults = raw.get("defaults")
        if paths is not None and not isinstance(paths, Mapping):
            raise TypeError(f"paths must be mapping, got {type(paths).__name__}")
        if server is not None and not isinstance(server, Mapping):
            raise TypeError(f"server must be mapping, got {type(server).__name__}")
        if defaults is not None and not isinstance(defaults, Mapping):
            raise TypeError(f"defaults must be mapping, got {type(defaults).__name__}")

        return cls(
            paths=PathsSettings.from_dict(paths),
            server=ServerSettings.from_dict(server),
            defaults=DefaultsSettings.from_dict(defaults),
            raw=raw,
        )
