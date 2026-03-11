from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import Settings, StrategyConfig


def _resolve_path(root: Path, p: Path) -> Path:
    return p if p.is_absolute() else (root / p).resolve()


def _parse_scalar(v: str) -> Any:
    s = v.strip()
    if s == "":
        return ""
    # Allow JSON-like inline structures in YAML subset (enables lists/dicts in strategy files
    # without requiring PyYAML). Example: separators: ["\\n\\n", "\\n", " ", ""]
    if (s.startswith("[") and s.endswith("]")) or (s.startswith("{") and s.endswith("}")):
        try:
            return json.loads(s)
        except Exception:
            # Fall back to raw string if parsing fails.
            pass
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


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _apply_model_endpoints(providers: dict[str, Any], endpoints: dict[str, Any]) -> dict[str, Any]:
    if not endpoints:
        return providers
    out: dict[str, Any] = dict(providers)
    for kind, value in list(out.items()):
        if not isinstance(value, dict):
            continue
        params = value.get("params")
        if params is None:
            params = {k: v for k, v in value.items() if k not in {"provider_id", "id"}}
        if not isinstance(params, dict):
            continue
        endpoint_key = params.get("endpoint_key") or params.get("endpoint")
        if not isinstance(endpoint_key, str) or not endpoint_key:
            continue
        # Strip indirection keys early so providers never need to accept them.
        params.pop("endpoint_key", None)
        params.pop("endpoint", None)

        ep = endpoints.get(endpoint_key)
        if not isinstance(ep, dict):
            value["params"] = params
            out[kind] = value
            continue
        # Fill missing base_url/api_key/deployment_name from endpoints.
        for key in ("base_url", "api_key", "deployment_name", "api_version"):
            if key not in params and key in ep:
                params[key] = ep[key]
        value["params"] = params
        out[kind] = value
    return out


def merge_provider_overrides(
    base: dict[str, Any],
    override: dict[str, Any] | None,
    endpoints: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not override:
        merged = dict(base)
    else:
        merged = dict(base)
        for kind, value in override.items():
            if kind in merged and isinstance(merged[kind], dict) and isinstance(value, dict):
                merged[kind] = _deep_merge(merged[kind], value)
            else:
                merged[kind] = value
    if endpoints:
        merged = _apply_model_endpoints(merged, endpoints)
    return merged


def load_settings(path: str | Path) -> Settings:
    """
    Load `config/settings.yaml` (workspace-local).

    A-1 scope: only settings loading + path normalization. More config (strategies/providers)
    will be added in later milestones.
    """
    p = Path(path).expanduser().resolve()
    root = p.parent.parent  # .../config/settings.yaml -> repo root

    raw = _load_yaml_mapping(p)

    # Optional private overrides (not committed). Controlled by env or default path.
    # For generated QA settings (`settings.qa.*.yaml`), skip implicit local overrides so
    # isolated runs are not polluted by developer-local experiments unless explicitly opted in.
    override_path = os.environ.get("MODULE_RAG_SECRETS_PATH")
    if override_path:
        ov = Path(override_path).expanduser()
    elif p.name.startswith("settings.qa."):
        ov = None
    else:
        ov = (p.parent / "local.override.yaml").resolve()
    if ov is not None and ov.exists() and ov.is_file():
        raw_override = _load_yaml_mapping(ov)
        raw = _deep_merge(raw, raw_override)

    # Optional model endpoints file (not committed).
    endpoints_path = os.environ.get("MODULE_RAG_MODEL_ENDPOINTS_PATH")
    if endpoints_path:
        ep = Path(endpoints_path).expanduser()
    else:
        ep = (p.parent / "model_endpoints.local.yaml").resolve()
    if ep.exists() and ep.is_file():
        raw_endpoints = _load_yaml_mapping(ep)
        if isinstance(raw_endpoints, dict) and "providers" in raw_endpoints:
            raw["model_endpoints"] = raw_endpoints.get("providers") or {}
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
