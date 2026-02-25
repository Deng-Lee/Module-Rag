from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import Settings, StrategyConfig


def _resolve_path(root: Path, p: Path) -> Path:
    return p if p.is_absolute() else (root / p).resolve()


def _parse_scalar(v: str) -> Any:
    s = v.strip()
    if s == "":
        return ""
    lo = s.lower()
    if lo in {"null", "~"}:
        return None
    if lo == "true":
        return True
    if lo == "false":
        return False
    if s.isdigit():
        return int(s)
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


def _simple_yaml_load(text: str) -> dict[str, Any]:
    """
    Minimal YAML subset loader (mappings only; 2-space indentation recommended).

    A-1 goal: keep the repo runnable in constrained environments where installing
    dependencies may be blocked. In real deployments we will prefer PyYAML.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent % 2 != 0:
            raise ValueError(f"invalid indentation (expected multiples of 2): {raw_line!r}")

        while stack and indent < stack[-1][0]:
            stack.pop()
        if not stack:
            raise ValueError(f"invalid indentation structure near: {raw_line!r}")

        cur = stack[-1][1]
        stripped = line.lstrip(" ")

        if ":" not in stripped:
            raise ValueError(f"invalid yaml line (missing ':'): {raw_line!r}")

        key, rest = stripped.split(":", 1)
        key = key.strip()
        if key == "":
            raise ValueError(f"invalid yaml key: {raw_line!r}")

        if rest.strip() == "":
            nxt: dict[str, Any] = {}
            cur[key] = nxt
            stack.append((indent + 2, nxt))
        else:
            cur[key] = _parse_scalar(rest)

    return root


def _load_yaml_mapping(p: Path) -> dict[str, Any]:
    # Prefer PyYAML if present; fall back to a tiny subset parser.
    try:
        import yaml  # type: ignore
    except Exception:
        return _simple_yaml_load(p.read_text(encoding="utf-8"))

    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise TypeError("settings root must be a mapping")
    return raw


def load_settings(path: str | Path) -> Settings:
    """
    Load `config/settings.yaml` (workspace-local).

    A-1 scope: only settings loading + path normalization. More config (strategies/providers)
    will be added in later milestones.
    """
    p = Path(path).expanduser().resolve()
    root = p.parent.parent  # .../config/settings.yaml -> repo root

    raw = _load_yaml_mapping(p)
    s = Settings.from_dict(raw)

    # normalize paths relative to repo root
    s.paths.data_dir = _resolve_path(root, s.paths.data_dir)
    s.paths.raw_dir = _resolve_path(root, s.paths.raw_dir)
    s.paths.md_dir = _resolve_path(root, s.paths.md_dir)
    s.paths.assets_dir = _resolve_path(root, s.paths.assets_dir)
    s.paths.chroma_dir = _resolve_path(root, s.paths.chroma_dir)
    s.paths.sqlite_dir = _resolve_path(root, s.paths.sqlite_dir)
    s.paths.cache_dir = _resolve_path(root, s.paths.cache_dir)
    s.paths.logs_dir = _resolve_path(root, s.paths.logs_dir)

    return s


class StrategyLoader:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            # .../src/core/strategy/loader.py -> repo root
            root = Path(__file__).resolve().parents[3]
        self.root = root
        self.strategies_dir = self.root / "config" / "strategies"

    def load(self, strategy_config_id: str) -> StrategyConfig:
        path = self._resolve_strategy_path(strategy_config_id)
        raw = _load_yaml_mapping(path)
        return StrategyConfig.from_dict(strategy_config_id, raw)

    def _resolve_strategy_path(self, strategy_config_id: str) -> Path:
        p = Path(strategy_config_id)
        if p.suffix in {".yml", ".yaml"}:
            if p.is_absolute():
                return p
            return (self.root / p).resolve()

        candidate = (self.strategies_dir / f"{strategy_config_id}.yaml").resolve()
        if candidate.exists():
            return candidate
        candidate_yml = (self.strategies_dir / f"{strategy_config_id}.yml").resolve()
        if candidate_yml.exists():
            return candidate_yml
        raise FileNotFoundError(f"strategy config not found: {strategy_config_id}")
