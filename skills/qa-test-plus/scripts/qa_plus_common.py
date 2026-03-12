from __future__ import annotations

import json
import math
import os
import socket
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REAL_COMPARE_DEFAULTS = (
    "local.default",
    "local.production_like",
    "local.production_like_cross_encoder",
)

FIXTURE_DOCS: tuple[tuple[str, str], ...] = (
    ("simple", "simple.pdf"),
    ("with_images", "with_images.pdf"),
    ("complex", "complex_technical_doc.pdf"),
    ("zh_technical", "chinese_technical_doc.pdf"),
    ("zh_long", "chinese_long_doc.pdf"),
)


@dataclass
class FailureInfo:
    stage: str | None = None
    location: str | None = None
    provider_model: str | None = None
    raw_error: str | None = None
    fallback: str | None = None


@dataclass
class CaseResult:
    case_id: str
    title: str
    entry: str
    strategy_config_id: str
    status: str
    evidence: dict[str, Any] = field(default_factory=dict)
    failure: FailureInfo = field(default_factory=FailureInfo)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["failure"] = asdict(self.failure)
        return out


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def script_dir() -> Path:
    return Path(__file__).resolve().parent


def ensure_repo_on_syspath() -> None:
    root = repo_root()
    sdir = script_dir()
    for entry in (str(sdir), str(root)):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def now_run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def slugify(value: str) -> str:
    out = []
    for ch in value:
        if ch.isalnum():
            out.append(ch.lower())
        else:
            out.append("-")
    text = "".join(out).strip("-")
    while "--" in text:
        text = text.replace("--", "-")
    return text or "default"


def yaml_dump_simple(d: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit_map(m: dict[str, Any], indent: int) -> None:
        pad = " " * indent
        for key, value in m.items():
            if isinstance(value, dict):
                lines.append(f"{pad}{key}:")
                emit_map(value, indent + 2)
            else:
                if isinstance(value, bool):
                    scalar = "true" if value else "false"
                elif isinstance(value, (list, tuple, dict)):
                    scalar = json.dumps(value, ensure_ascii=False)
                else:
                    scalar = str(value)
                lines.append(f"{pad}{key}: {scalar}")

    emit_map(d, 0)
    return "\n".join(lines) + "\n"


def settings_path_for(run_id: str, suffix: str = "main") -> Path:
    return repo_root() / "config" / f"settings.qa.plus.{run_id}.{suffix}.yaml"


def run_root_for(run_id: str, suffix: str = "main") -> Path:
    return repo_root() / "data" / "qa_plus_runs" / run_id / suffix


def strategy_path_for(run_id: str, name: str) -> Path:
    return run_root_for(run_id, "strategies") / f"{slugify(name)}.yaml"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        cur = out.get(key)
        if isinstance(cur, dict) and isinstance(value, dict):
            out[key] = deep_merge(cur, value)
        else:
            out[key] = value
    return out


def write_real_settings(
    path: Path,
    *,
    run_id: str,
    suffix: str,
    strategy_config_id: str,
    providers_override: dict[str, Any] | None = None,
) -> None:
    root = repo_root()
    data_root = root / "data" / "qa_plus_runs" / run_id / suffix
    cache_root = root / "cache" / "qa_plus_runs" / run_id / suffix
    logs_root = root / "logs" / "qa_plus_runs" / run_id / suffix
    payload = {
        "paths": {
            "data_dir": str(data_root),
            "raw_dir": str(data_root / "raw"),
            "md_dir": str(data_root / "md"),
            "assets_dir": str(data_root / "assets"),
            "chroma_dir": str(data_root / "chroma"),
            "sqlite_dir": str(data_root / "sqlite"),
            "cache_dir": str(cache_root),
            "logs_dir": str(logs_root),
        },
        "server": {
            "dashboard_host": "127.0.0.1",
            "dashboard_port": 7860,
        },
        "defaults": {"strategy_config_id": strategy_config_id},
        "eval": {"datasets_dir": "tests/datasets"},
        "providers": {
            "embedder": {"params": {"timeout_s": 20}},
            "llm": {"params": {"timeout_s": 30}},
            "judge": {
                "provider_id": "openai_compatible",
                "params": {
                    "endpoint_key": "qwen",
                    "model": "qwen-turbo",
                    "timeout_s": 30,
                },
            },
            "evaluator": {
                "provider_id": "ragas",
                "params": {
                    "endpoint_key": "qwen",
                    "model": "qwen3.5-plus",
                    "embedding_model": "text-embedding-v3",
                },
            },
            "enricher": {"provider_id": "noop"},
        },
    }
    if providers_override:
        payload["providers"] = deep_merge(payload["providers"], providers_override)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# qa-test-plus generated settings\n"
        "# do not commit\n"
        f"# run_id: {run_id}\n" + yaml_dump_simple(payload),
        encoding="utf-8",
    )


def activate_runtime(settings_path: Path) -> Any:
    ensure_repo_on_syspath()
    os.environ["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)

    from src.core.strategy import load_settings
    from src.observability.obs import api as obs
    from src.observability.sinks.jsonl import JsonlSink

    settings = load_settings(settings_path)
    obs.set_sink(JsonlSink(settings.paths.logs_dir))
    return settings


def load_strategy_config(strategy_config_id: str) -> Any:
    ensure_repo_on_syspath()
    from src.core.strategy.loader import StrategyLoader

    return StrategyLoader(repo_root()).load(strategy_config_id)


def write_strategy_yaml(
    path: Path,
    *,
    base_strategy_id: str,
    raw_override: dict[str, Any],
) -> Path:
    strategy = load_strategy_config(base_strategy_id)
    merged = deep_merge(dict(strategy.raw), raw_override)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml_dump_simple(merged), encoding="utf-8")
    return path


def merged_provider_specs(settings: Any, strategy_config_id: str) -> dict[str, Any]:
    ensure_repo_on_syspath()
    from src.core.strategy import merge_provider_overrides

    strategy = load_strategy_config(strategy_config_id)
    base = settings.raw.get("providers") or {}
    endpoints = settings.raw.get("model_endpoints") or {}
    return merge_provider_overrides(base, strategy.providers, endpoints)


def fixture_path(filename: str) -> Path:
    return repo_root() / "tests" / "fixtures" / "sample_documents" / filename


def json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def json_loads_safe(raw: str | None) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def host_from_base_url(base_url: str) -> str:
    text = (base_url or "").strip()
    text = text.replace("https://", "").replace("http://", "")
    text = text.split("/")[0]
    return text.split(":")[0]


def dns_check(host: str) -> tuple[bool, str]:
    try:
        socket.getaddrinfo(host, 443)
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def provider_model_label(provider_id: str | None, params: dict[str, Any] | None) -> str:
    params = params or {}
    model = (
        params.get("model") or params.get("model_name") or params.get("deployment_name") or "n/a"
    )
    return f"{provider_id or 'unknown'}::{model}"


def build_failure(
    *,
    stage: str,
    location: str,
    provider_model: str,
    raw_error: str,
    fallback: str = "not_triggered",
) -> FailureInfo:
    return FailureInfo(
        stage=stage,
        location=location,
        provider_model=provider_model,
        raw_error=raw_error,
        fallback=fallback,
    )


def summary_counts(cases: list[CaseResult]) -> dict[str, int]:
    counts = {"PASS": 0, "FAIL": 0, "BLOCKED": 0}
    for case in cases:
        if case.status.startswith("BLOCKED"):
            counts["BLOCKED"] += 1
        elif case.status.startswith("FAIL"):
            counts["FAIL"] += 1
        elif case.status.startswith("PASS"):
            counts["PASS"] += 1
    counts["TOTAL"] = len(cases)
    return counts


def traces_have_event(trace: Any, span_name: str, kind_substring: str) -> bool:
    if trace is None:
        return False
    spans = getattr(trace, "spans", None) or []
    for span in spans:
        if getattr(span, "name", None) != span_name:
            continue
        for event in getattr(span, "events", None) or []:
            kind = str(getattr(event, "kind", "") or "")
            if kind_substring in kind:
                return True
    return False


def find_error_event(trace: Any) -> dict[str, Any] | None:
    if trace is None:
        return None
    for span in getattr(trace, "spans", None) or []:
        for event in getattr(span, "events", None) or []:
            kind = str(getattr(event, "kind", "") or "")
            if "error" in kind:
                return {
                    "span": getattr(span, "name", None),
                    "kind": kind,
                    "attrs": getattr(event, "attrs", None) or {},
                }
    return None


def safe_metric_dict(metrics: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    clean: dict[str, Any] = {}
    nan_keys: list[str] = []
    for key, value in (metrics or {}).items():
        if isinstance(value, float) and math.isnan(value):
            nan_keys.append(key)
            clean[key] = "NaN"
        else:
            clean[key] = value
    return clean, nan_keys


def preflight_real(
    settings_path: Path, strategy_config_id: str
) -> tuple[str, dict[str, Any], FailureInfo | None]:
    try:
        settings = activate_runtime(settings_path)
        merged = merged_provider_specs(settings, strategy_config_id)
    except Exception as exc:
        return (
            "FAIL",
            {},
            build_failure(
                stage="config_load",
                location="qa_plus_common.preflight_real",
                provider_model="n/a",
                raw_error=f"{type(exc).__name__}: {exc}",
            ),
        )

    checks: list[dict[str, Any]] = []
    for kind in ("embedder", "llm", "judge", "evaluator", "reranker"):
        spec = merged.get(kind)
        if not isinstance(spec, dict):
            continue
        provider_id = str(spec.get("provider_id") or spec.get("id") or "")
        params = spec.get("params") if isinstance(spec.get("params"), dict) else {}
        if provider_id in {"noop", "fake", "fake_alt", "cross_encoder"}:
            checks.append(
                {
                    "kind": kind,
                    "provider_id": provider_id,
                    "model": params.get("model") or params.get("model_name") or "",
                    "status": "SKIP",
                    "reason": "non_network_provider",
                }
            )
            continue
        base_url = str(params.get("base_url") or "")
        api_key = str(params.get("api_key") or "")
        host = host_from_base_url(base_url) if base_url else ""
        status = "PASS"
        reason = ""
        if not api_key:
            status = "FAIL"
            reason = "missing_api_key"
        elif host:
            ok, msg = dns_check(host)
            if not ok:
                status = "BLOCKED(env:network)"
                reason = msg
        checks.append(
            {
                "kind": kind,
                "provider_id": provider_id,
                "model": params.get("model") or params.get("model_name") or "",
                "host": host,
                "status": status,
                "reason": reason,
            }
        )

    blocked = next((c for c in checks if str(c["status"]).startswith("BLOCKED")), None)
    failed = next((c for c in checks if str(c["status"]).startswith("FAIL")), None)
    if blocked:
        return (
            "BLOCKED(env:network)",
            {"checks": checks},
            build_failure(
                stage="preflight_dns",
                location="qa_plus_common.preflight_real",
                provider_model=(
                    f"{blocked['kind']}::{blocked['provider_id']}::{blocked.get('model') or 'n/a'}"
                ),
                raw_error=str(blocked.get("reason") or "dns_failure"),
                fallback="not_triggered",
            ),
        )
    if failed:
        return (
            "FAIL",
            {"checks": checks},
            build_failure(
                stage="preflight_config",
                location="qa_plus_common.preflight_real",
                provider_model=(
                    f"{failed['kind']}::{failed['provider_id']}::{failed.get('model') or 'n/a'}"
                ),
                raw_error=str(failed.get("reason") or "provider_config_invalid"),
                fallback="not_triggered",
            ),
        )
    return "PASS", {"checks": checks}, None
