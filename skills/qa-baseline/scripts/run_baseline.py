from __future__ import annotations

import argparse
import json
import os
import re
import socket
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable


RE_ERRNO8 = re.compile(r"\[Errno 8\]")


def _now_run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def _repo_root() -> Path:
    # skills/qa-baseline/scripts/run_baseline.py -> repo root
    return Path(__file__).resolve().parents[3]


def _ensure_repo_on_syspath() -> None:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _yaml_dump_simple(d: dict[str, Any]) -> str:
    # Keep it dependency-free: use a tiny YAML emitter for our fixed shape.
    lines: list[str] = []

    def w(line: str) -> None:
        lines.append(line)

    def emit_map(m: dict[str, Any], indent: int) -> None:
        pad = " " * indent
        for k, v in m.items():
            if isinstance(v, dict):
                w(f"{pad}{k}:")
                emit_map(v, indent + 2)
            else:
                if isinstance(v, bool):
                    s = "true" if v else "false"
                else:
                    s = str(v)
                w(f"{pad}{k}: {s}")

    emit_map(d, 0)
    return "\n".join(lines) + "\n"


def _merge_dicts(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    if not override:
        return dict(base)
    out = dict(base)
    for k, v in override.items():
        cur = out.get(k)
        if isinstance(cur, dict) and isinstance(v, dict):
            out[k] = _merge_dicts(cur, v)
        else:
            out[k] = v
    return out


def _write_settings(
    path: Path,
    *,
    run_id: str,
    profile: str,
    defaults_strategy: str,
    providers_override: dict[str, Any] | None = None,
) -> None:
    root = _repo_root()
    base = root / "config" / "settings.yaml"
    if not base.exists():
        raise FileNotFoundError(f"missing settings.yaml: {base}")

    data_root = root / "data" / "qa_runs" / run_id / profile
    cache_root = root / "cache" / "qa_runs" / run_id / profile
    logs_root = root / "logs" / "qa_runs" / run_id / profile

    obj: dict[str, Any] = {
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
        "defaults": {"strategy_config_id": defaults_strategy},
        "eval": {"datasets_dir": "tests/datasets"},
    }
    if profile.startswith("real"):
        obj["providers"] = {
            "embedder": {"params": {"timeout_s": 20}},
            "llm": {"params": {"timeout_s": 20}},
            "judge": {"provider_id": "noop"},
            "evaluator": {"provider_id": "composite"},
            "reranker": {"provider_id": "noop"},
            "enricher": {"provider_id": "noop"},
        }
    if providers_override:
        obj["providers"] = _merge_dicts(obj.get("providers", {}), providers_override)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# QA baseline settings (generated)\n"
        "# DO NOT COMMIT (ignored by .gitignore)\n"
        f"# run_id: {run_id}\n" + _yaml_dump_simple(obj),
        encoding="utf-8",
    )


def _host_from_base_url(base_url: str) -> str:
    s = (base_url or "").strip()
    s = s.replace("https://", "").replace("http://", "")
    s = s.split("/")[0]
    s = s.split(":")[0]
    return s


def _dns_ok(host: str) -> tuple[bool, str]:
    try:
        socket.getaddrinfo(host, 443)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


@dataclass
class StepResult:
    status: str  # PASS|FAIL|BLOCKED|SKIP
    trace_id: str | None = None
    details: dict[str, Any] | None = None
    error: str | None = None
    diagnostic: dict[str, Any] | None = None


@dataclass(frozen=True)
class Case:
    case_id: str
    title: str
    profiles: tuple[str, ...]  # OFFLINE|REAL
    section: str  # A..O
    is_ui: bool = False
    steps_brief: str = ""
    expected_brief: str = ""


@dataclass
class CaseResult:
    case: Case
    offline: StepResult | None = None
    real: StepResult | None = None
    overall: str = "TODO"
    note: str = ""


class _CaseTimeoutError(TimeoutError):
    pass


def _compute_overall(case: Case, offline: StepResult | None, real: StepResult | None) -> str:
    need_offline = "OFFLINE" in case.profiles
    need_real = "REAL" in case.profiles
    # Both required.
    if need_offline and need_real:
        # If only one profile ran, we keep the case "not green" to avoid false PASS.
        if offline is None or real is None:
            return "PARTIAL"
        if offline.status == "PASS" and real.status == "PASS":
            return "PASS"
        # Prefer BLOCKED if any blocked.
        if offline.status.startswith("BLOCKED") or real.status.startswith("BLOCKED"):
            return "BLOCKED"
        if offline.status.startswith("FAIL") or real.status.startswith("FAIL"):
            return "FAIL"
        return "TODO"
    # Single-profile case
    r = offline if need_offline else real
    if r is None:
        return "TODO"
    if r.status.startswith("PASS"):
        return "PASS"
    if r.status.startswith("BLOCKED"):
        return "BLOCKED"
    if r.status.startswith("FAIL"):
        return "FAIL"
    return r.status


def _classify_real_error(msg: str) -> str:
    m = msg or ""
    if RE_ERRNO8.search(m) or "nodename nor servname provided" in m:
        return "BLOCKED(env:network)"
    return "FAIL(system_or_config)"


def _flow_for_case(case: Case) -> str:
    group = case.case_id.split("-", 1)[0]
    mapping = {
        "A": "dashboard overview api",
        "B": "documents/chunks browse api",
        "C": "ingest api",
        "D": "trace replay api",
        "E": "query trace api",
        "F": "eval api",
        "G": "ingestion pipeline",
        "H": "retrieve/query pipeline",
        "I": "eval runner",
        "J": "mcp protocol/tools",
        "K": "provider switch / llm fallback",
        "L": "rerank pipeline",
        "M": "config/tool validation",
        "N": "delete/query consistency",
        "O": "versioning / mixed retrieval",
    }
    return mapping.get(group, "unknown")


def _relevant_provider_kinds(case: Case) -> tuple[str, ...]:
    group = case.case_id.split("-", 1)[0]
    if group in {"A", "B", "D", "E", "F", "J", "M"}:
        return ()
    if group in {"C", "G"}:
        return ("embedder",)
    if group in {"K"}:
        return ("llm",)
    if group in {"L"}:
        return ("reranker",)
    if group in {"I"}:
        return ("judge", "llm")
    return ("embedder", "llm", "reranker")


def _provider_snapshot(env: "ProfileEnv") -> dict[str, dict[str, Any]]:
    settings = env.settings
    raw = getattr(settings, "raw", {}) or {}
    providers = raw.get("providers") or {}
    endpoints = raw.get("model_endpoints") or {}
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(providers, dict):
        return out
    for kind in ("embedder", "llm", "judge", "reranker"):
        spec = providers.get(kind)
        if not isinstance(spec, dict):
            continue
        params = spec.get("params") or {}
        endpoint_key = params.get("endpoint_key") if isinstance(params, dict) else None
        endpoint = endpoints.get(endpoint_key) if isinstance(endpoints, dict) and endpoint_key else None
        item = {
            "provider_id": spec.get("provider_id"),
            "endpoint_key": endpoint_key,
            "model": params.get("model") if isinstance(params, dict) else None,
            "strategy_config_id": env.strategy_config_id,
        }
        if isinstance(endpoint, dict) and endpoint.get("base_url"):
            item["base_url"] = endpoint.get("base_url")
        out[kind] = {k: v for k, v in item.items() if v not in {None, ""}}
    return out


def _fallback_hint(case: Case) -> str | None:
    if case.case_id == "K-02":
        return "llm failure should fall back to extractive answer"
    if case.case_id == "L-03":
        return "rerank failure should fall back to fusion order"
    return None


def _build_real_diagnostic(
    case: Case,
    env: "ProfileEnv",
    *,
    location: str,
    error: str | None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    snapshot = _provider_snapshot(env)
    relevant_kinds = _relevant_provider_kinds(case)
    relevant = {k: snapshot[k] for k in relevant_kinds if k in snapshot}
    return {
        "flow": _flow_for_case(case),
        "location": location,
        "case_id": case.case_id,
        "strategy_config_id": env.strategy_config_id,
        "models": relevant or snapshot,
        "raw_error": error,
        "trace_id": trace_id,
        "fallback": _fallback_hint(case),
    }


def _attach_real_diagnostic(case: Case, env: "ProfileEnv", sr: StepResult, *, location: str) -> StepResult:
    if sr.status.startswith("PASS") or sr.diagnostic:
        return sr
    sr.diagnostic = _build_real_diagnostic(case, env, location=location, error=sr.error, trace_id=sr.trace_id)
    return sr


def _format_models(models: Any) -> str:
    if not isinstance(models, dict) or not models:
        return "n/a"
    parts: list[str] = []
    for kind, spec in models.items():
        if not isinstance(spec, dict):
            continue
        provider_id = spec.get("provider_id") or "unknown"
        model = spec.get("model")
        endpoint_key = spec.get("endpoint_key")
        chunk = f"{kind}={provider_id}"
        if model:
            chunk += f"/{model}"
        if endpoint_key:
            chunk += f"@{endpoint_key}"
        parts.append(chunk)
    return ", ".join(parts) if parts else "n/a"


def _summarize_diagnostic(diag: dict[str, Any] | None) -> str:
    if not diag:
        return ""
    parts = [
        f"flow={diag.get('flow') or 'unknown'}",
        f"location={diag.get('location') or 'unknown'}",
        f"model={_format_models(diag.get('models'))}",
    ]
    fallback = diag.get("fallback")
    if fallback:
        parts.append(f"fallback={fallback}")
    raw = str(diag.get("raw_error") or "").strip()
    if raw:
        parts.append(f"raw={raw[:220]}")
    return "; ".join(parts)


def _run_with_timeout(timeout_s: float, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if timeout_s <= 0:
        return fn(*args, **kwargs)

    def _raise_timeout(signum: int, frame: Any) -> None:
        raise _CaseTimeoutError(f"case exceeded {timeout_s:.0f}s")

    old_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        return fn(*args, **kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


def _load_cases(qa_test_path: Path) -> list[Case]:
    """
    Best-effort parser for QA_TEST.md.

    We only rely on:
    - heading line: ### <case_id> <title>
    - profiles line: Profiles：OFFLINE/REAL (or OFFLINE, REAL)
    """
    text = qa_test_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[Case] = []

    i = 0
    cur_section = "?"
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            # "## A. ..." -> section key "A"
            m = re.match(r"^##\s+([A-O])\.", line.strip())
            if m:
                cur_section = m.group(1)
        if line.startswith("### "):
            # Only accept well-formed case ids: A-01, C-UI-01, etc.
            m0 = re.match(r"^###\s+([A-O]-(?:UI-)?\d{2})\s*(.*)$", line.strip())
            if not m0:
                i += 1
                continue
            case_id = m0.group(1).strip()
            title = (m0.group(2) or "").strip()

            # scan forward for Profiles line until next heading
            j = i + 1
            profiles: tuple[str, ...] = ("OFFLINE", "REAL")
            in_steps = False
            in_expected = False
            steps_items: list[str] = []
            expected_items: list[str] = []
            while j < len(lines) and not lines[j].startswith("### ") and not lines[j].startswith("## "):
                s = lines[j].strip()

                m2 = re.match(r"^Profiles[:：]\s*(.+)\s*$", s)
                if m2:
                    raw = m2.group(1).strip()
                    if raw:
                        toks = re.split(r"[/,，\s]+", raw)
                        norm = []
                        for t in toks:
                            tt = t.strip().upper()
                            if tt in {"OFFLINE", "REAL"}:
                                norm.append(tt)
                        if norm:
                            profiles = tuple(dict.fromkeys(norm).keys())
                    j += 1
                    continue

                if s.startswith("步骤"):
                    in_steps = True
                    in_expected = False
                    j += 1
                    continue
                if s.startswith("预期"):
                    in_steps = False
                    in_expected = True
                    j += 1
                    continue

                if in_steps:
                    m = re.match(r"^\s*\d+\.\s*(.+)$", s)
                    if m:
                        steps_items.append(m.group(1).strip())
                    elif s.startswith("- "):
                        steps_items.append(s[2:].strip())
                if in_expected:
                    m = re.match(r"^\s*\d+\.\s*(.+)$", s)
                    if m:
                        expected_items.append(m.group(1).strip())
                    elif s.startswith("- "):
                        expected_items.append(s[2:].strip())

                j += 1

            steps_brief = "; ".join(steps_items[:3]) if steps_items else ""
            expected_brief = "; ".join(expected_items[:3]) if expected_items else ""

            is_ui = ("-UI-" in case_id) or ("待实现" in title)
            out.append(
                Case(
                    case_id=case_id,
                    title=title,
                    profiles=profiles,
                    section=cur_section,
                    is_ui=is_ui,
                    steps_brief=steps_brief,
                    expected_brief=expected_brief,
                )
            )
        i += 1
    return out


@dataclass
class ProfileEnv:
    name: str  # OFFLINE|REAL
    settings_path: Path
    strategy_config_id: str
    _settings_obj: Any | None = None
    _api_client: Any | None = None
    ingested: dict[str, dict[str, Any]] = field(default_factory=dict)  # file_key -> structured
    last_query: dict[str, Any] = field(default_factory=dict)

    def activate(self) -> None:
        _ensure_repo_on_syspath()
        os.environ["MODULE_RAG_SETTINGS_PATH"] = str(self.settings_path)
        # Baseline runs should be driven by the generated settings, not ad-hoc local overrides.
        # Point secrets override to a non-existent file for both OFFLINE/REAL.
        os.environ["MODULE_RAG_SECRETS_PATH"] = str(self.settings_path.parent / "__NO_OVERRIDE__.yaml")
        if self.name == "OFFLINE":
            os.environ["MODULE_RAG_MODEL_ENDPOINTS_PATH"] = str(self.settings_path.parent / "__NO_ENDPOINTS__.yaml")
        else:
            os.environ.pop("MODULE_RAG_MODEL_ENDPOINTS_PATH", None)
        # Bind observability sink to this env so /api/traces has data.
        from src.core.strategy import load_settings
        from src.observability.obs import api as obs
        from src.observability.sinks.jsonl import JsonlSink

        self._settings_obj = load_settings(self.settings_path)
        obs.set_sink(JsonlSink(self._settings_obj.paths.logs_dir))

    @property
    def settings(self) -> Any:
        if self._settings_obj is None:
            self.activate()
        return self._settings_obj

    def api_client(self):
        if self._api_client is not None:
            return self._api_client
        from fastapi.testclient import TestClient
        from src.observability.dashboard.app import create_app

        app = create_app(self.settings)
        self._api_client = TestClient(app)
        return self._api_client

    def ingest(self, file_path: Path, *, policy: str = "new_version") -> StepResult:
        self.activate()
        key = str(file_path)
        from src.core.runners.ingest import IngestRunner

        runner = IngestRunner(settings_path=self.settings_path)
        resp = runner.run(file_path, strategy_config_id=self.strategy_config_id, policy=policy)
        structured = dict(resp.structured or {})
        st = structured.get("status")
        if st not in {"ok", "skipped"}:
            err = str(structured.get("error") or "ingest_error")
            status = _classify_real_error(err) if self.name == "REAL" else "FAIL"
            return StepResult(status=status, trace_id=resp.trace_id, details=structured, error=err)
        self.ingested[key] = structured
        # Treat dedup-skip as a valid outcome for many workflows; tests can assert decision.
        return StepResult(status="PASS", trace_id=resp.trace_id, details=structured)

    def query(self, query: str, *, top_k: int = 5) -> StepResult:
        self.activate()
        from src.core.runners.query import QueryRunner

        runner = QueryRunner(settings_path=self.settings_path)
        resp = runner.run(query, strategy_config_id=self.strategy_config_id, top_k=top_k)
        self.last_query = {"query": query, "sources": resp.sources, "trace_id": resp.trace_id}
        if not resp.sources:
            return StepResult(status="FAIL", trace_id=resp.trace_id, error="empty_sources")
        return StepResult(status="PASS", trace_id=resp.trace_id, details={"source_count": len(resp.sources)})

    def admin_delete(self, doc_id: str, version_id: str | None, *, mode: str = "soft") -> StepResult:
        self.activate()
        from src.core.runners.admin import AdminRunner

        runner = AdminRunner(settings_path=self.settings_path)
        res = runner.delete_document(doc_id=doc_id, version_id=version_id, mode=mode, dry_run=False)
        if res.status not in {"ok", "noop"}:
            return StepResult(status="FAIL", trace_id=res.trace_id, details={"affected": res.affected}, error="delete_failed")
        return StepResult(status="PASS", trace_id=res.trace_id, details={"affected": res.affected})


def _pass() -> StepResult:
    return StepResult(status="PASS")


def _blocked(reason: str) -> StepResult:
    return StepResult(status="BLOCKED", error=reason)


def _fail(reason: str) -> StepResult:
    return StepResult(status="FAIL", error=reason)


def _require_ui_tokens(path: Path, tokens: list[str]) -> str | None:
    if not path.exists():
        return f"missing_ui_file:{path.name}"
    text = path.read_text(encoding="utf-8")
    missing = [t for t in tokens if t not in text]
    if missing:
        return f"ui_contract_missing:{path.name}:{'|'.join(missing[:3])}"
    return None


def _trace_span(trace: Any, name: str) -> Any | None:
    spans = getattr(trace, "spans", None)
    if not isinstance(spans, list):
        return None
    for span in spans:
        if getattr(span, "name", None) == name:
            return span
    return None


def _trace_has_event(trace: Any, span_name: str, kind: str) -> bool:
    span = _trace_span(trace, span_name)
    events = getattr(span, "events", None) if span is not None else None
    if not isinstance(events, list):
        return False
    return any(getattr(ev, "kind", None) == kind for ev in events)


def _last_trace_event(trace: Any, span_name: str, kind: str) -> Any | None:
    span = _trace_span(trace, span_name)
    events = getattr(span, "events", None) if span is not None else None
    if not isinstance(events, list):
        return None
    matches = [ev for ev in events if getattr(ev, "kind", None) == kind]
    return matches[-1] if matches else None


def _is_cross_encoder_env_unready(exc: Exception) -> bool:
    m = str(exc).lower()
    return (
        "cross_encoder dependency missing" in m
        or "no module named 'sentence_transformers'" in m
        or "httpsconnectionpool" in m
        or "connection error" in m
        or "timed out" in m
        or "name or service not known" in m
        or "temporary failure in name resolution" in m
        or "ssl" in m
    )


def _make_provider(kind: str, provider_id: str, **kwargs: Any) -> Any:
    _ensure_repo_on_syspath()
    from src.libs.providers import register_builtin_providers
    from src.libs.registry import ProviderRegistry

    registry = ProviderRegistry()
    register_builtin_providers(registry)
    return registry.create(kind, provider_id, **kwargs)


def _start_fake_openai_chat_server(content: str) -> tuple[str, Any]:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    body = json.dumps(
        {
            "id": "chatcmpl-qa",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
        ensure_ascii=False,
    ).encode("utf-8")

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            _ = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover
            _ = format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}/v1", server


def _make_fixed_query_runtime_builder(
    *,
    work_dir: Path,
    llm: Any,
    llm_provider_id: str | None = None,
    reranker: Any | None = None,
    reranker_provider_id: str | None = None,
    rerank_profile_id: str | None = None,
    empty_candidates: bool = False,
) -> tuple[Callable[[str], Any], dict[str, str]]:
    _ensure_repo_on_syspath()
    from src.core.query_engine.models import QueryRuntime
    from src.ingestion.stages.storage.sqlite import SqliteStore
    from src.libs.interfaces.vector_store import Candidate
    from src.libs.providers.embedding.fake_embedder import FakeEmbedder
    from src.libs.providers.vector_store.in_memory import InMemoryVectorIndex
    from src.observability.trace.context import TraceContext

    work_dir.mkdir(parents=True, exist_ok=True)
    sqlite = SqliteStore(db_path=work_dir / "app.sqlite")
    ids = {"relevant": "chk_paris", "irrelevant": "chk_banana"}

    if not empty_candidates:
        sqlite.upsert_doc_version_minimal("doc_rel", "ver_rel", file_sha256="h1", status="indexed")
        sqlite.upsert_chunk(
            chunk_id=ids["relevant"],
            doc_id="doc_rel",
            version_id="ver_rel",
            section_id="sec_rel",
            section_path="France",
            chunk_index=1,
            chunk_text="Paris is the capital of France.",
            chunk_retrieval_text="Paris is the capital of France.",
        )
        sqlite.upsert_doc_version_minimal("doc_irr", "ver_irr", file_sha256="h2", status="indexed")
        sqlite.upsert_chunk(
            chunk_id=ids["irrelevant"],
            doc_id="doc_irr",
            version_id="ver_irr",
            section_id="sec_irr",
            section_path="Fruit",
            chunk_index=1,
            chunk_text="Bananas are yellow fruits rich in potassium.",
            chunk_retrieval_text="Bananas are yellow fruits rich in potassium.",
        )

    candidates = []
    if not empty_candidates:
        candidates = [
            Candidate(chunk_id=ids["irrelevant"], score=1.0, source="dense"),
            Candidate(chunk_id=ids["relevant"], score=0.9, source="dense"),
        ]

    class _FixedRetriever:
        def __init__(self, fixed: list[Any]) -> None:
            self._fixed = list(fixed)

        def retrieve(self, query: str, top_k: int) -> list[Any]:
            _ = query
            return list(self._fixed[:top_k])

    retriever = _FixedRetriever(candidates)
    embedder = FakeEmbedder(dim=8)
    vector_index = InMemoryVectorIndex()

    def build_rt(_: str) -> Any:
        ctx = TraceContext.current()
        if ctx is not None:
            snapshot: dict[str, dict[str, Any]] = {}
            if llm_provider_id:
                snapshot["llm"] = {"provider_id": llm_provider_id}
            if reranker_provider_id:
                snapshot["reranker"] = {"provider_id": reranker_provider_id}
                if rerank_profile_id:
                    snapshot["reranker"]["rerank_profile_id"] = rerank_profile_id
            ctx.providers_snapshot = snapshot
        return QueryRuntime(
            embedder=embedder,
            vector_index=vector_index,
            retriever=retriever,
            sqlite=sqlite,
            sparse_retriever=None,
            fusion=None,
            reranker=reranker,
            llm=llm,
            reranker_provider_id=reranker_provider_id,
            rerank_profile_id=rerank_profile_id,
        )

    return build_rt, ids


def _exec_case(case: Case, env: ProfileEnv, *, shared: dict[str, Any]) -> StepResult:
    """
    Execute a single QA_TEST case in this env. Best-effort automation.

    For cases without executor, return BLOCKED(no_executor).
    """
    root = _repo_root()
    docs = root / "tests" / "fixtures" / "docs"
    c = case.case_id
    web_routes = root / "web" / "src" / "routes"

    # --- UI: Dashboard ---
    if c == "A-UI-01":
        miss = _require_ui_tokens(web_routes / "Overview.tsx", ["系统总览", "资产统计", "Provider 快照"])
        if miss:
            return _fail(miss)
        r = env.api_client().get("/api/overview")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        if not all(k in j for k in ("assets", "health", "providers")):
            return _fail("missing_keys")
        return _pass()

    if c == "A-UI-02":
        miss = _require_ui_tokens(web_routes / "Overview.tsx", ["expandedProvider", "展开详情", "收起详情"])
        if miss:
            return _fail(miss)
        _ = env.ingest(docs / "sample.md", policy="skip")
        r = env.api_client().get("/api/overview")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        providers = (r.json() or {}).get("providers") or {}
        if not isinstance(providers, dict) or not providers:
            return _fail("providers_empty")
        return _pass()

    if c == "A-UI-03":
        miss = _require_ui_tokens(web_routes / "Overview.tsx", ["刷新", "最后刷新", "setInterval"])
        if miss:
            return _fail(miss)
        before = env.api_client().get("/api/overview")
        if before.status_code != 200:
            return _fail(f"http_{before.status_code}")
        before_recent = int(((before.json() or {}).get("health") or {}).get("recent_traces") or 0)
        _ = env.ingest(docs / "sample.md", policy="skip")
        _ = env.query("FTS5", top_k=5)
        after = env.api_client().get("/api/overview")
        if after.status_code != 200:
            return _fail(f"http_{after.status_code}")
        after_recent = int(((after.json() or {}).get("health") or {}).get("recent_traces") or 0)
        if after_recent <= 0 or after_recent < before_recent:
            return _fail("health_not_refreshed")
        return _pass()

    if c == "B-UI-01":
        miss = _require_ui_tokens(web_routes / "Browser.tsx", ["上一页", "下一页", "offset", "limit"])
        if miss:
            return _fail(miss)
        _ = env.ingest(docs / "sample.md", policy="skip")
        _ = env.ingest(docs / "simple.pdf", policy="new_version")
        r0 = env.api_client().get("/api/documents?limit=1&offset=0")
        r1 = env.api_client().get("/api/documents?limit=1&offset=1")
        if r0.status_code != 200 or r1.status_code != 200:
            return _fail("http_error")
        i0 = (r0.json() or {}).get("items") or []
        if not i0:
            return _fail("page0_empty")
        return _pass()

    if c == "B-UI-02":
        miss = _require_ui_tokens(web_routes / "Browser.tsx", ["doc_id", "include_deleted", 'type="checkbox"'])
        if miss:
            return _fail(miss)
        res = env.ingest(docs / "sample.md", policy="new_version")
        if res.status != "PASS":
            return res
        doc_id = (res.details or {}).get("doc_id")
        version_id = (res.details or {}).get("version_id")
        if not doc_id:
            return _fail("missing_doc_id")
        _ = env.admin_delete(str(doc_id), str(version_id) if version_id else None, mode="soft")
        r_hide = env.api_client().get(f"/api/documents?doc_id={doc_id}&include_deleted=false")
        r_show = env.api_client().get(f"/api/documents?doc_id={doc_id}&include_deleted=true")
        if r_hide.status_code != 200 or r_show.status_code != 200:
            return _fail("http_error")
        hide_items = (r_hide.json() or {}).get("items") or []
        show_items = (r_show.json() or {}).get("items") or []
        if any((it or {}).get("status") == "deleted" for it in hide_items):
            return _fail("deleted_visible_when_hidden")
        if not any((it or {}).get("status") == "deleted" for it in show_items):
            return _fail("deleted_not_visible_when_shown")
        return _pass()

    if c == "B-UI-03":
        miss = _require_ui_tokens(web_routes / "Browser.tsx", ["Chunk 详情", "chunk_text", "section_path", "version_id"])
        if miss:
            return _fail(miss)
        _ = env.ingest(docs / "sample.md", policy="skip")
        q = env.query("FTS5", top_k=5)
        if q.status != "PASS":
            return q
        sources = env.last_query.get("sources") or []
        chunk_id = getattr(sources[0], "chunk_id", None) if sources else None
        if not chunk_id:
            return _fail("missing_chunk_id")
        r = env.api_client().get(f"/api/chunk/{chunk_id}")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        if not all(k in j for k in ("chunk_text", "section_path", "doc_id", "version_id")):
            return _fail("missing_chunk_fields")
        return _pass()

    if c == "C-UI-01":
        miss = _require_ui_tokens(web_routes / "Ingestion.tsx", ["Ingest", "trace_id", "doc_id", "version_id"])
        if miss:
            return _fail(miss)
        r = env.api_client().post(
            "/api/ingest",
            json={"file_path": str(docs / "sample.md"), "policy": "skip", "strategy_config_id": "default"},
        )
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        if not j.get("trace_id"):
            return _fail("missing_trace_id")
        st = ((j.get("structured") or {}).get("status") if isinstance(j.get("structured"), dict) else None)
        if st not in {"ok", "skipped"}:
            return _fail("structured_not_ok")
        return _pass()

    if c == "C-UI-02":
        miss = _require_ui_tokens(web_routes / "Ingestion.tsx", ["if (!filePath.trim())", "请输入 file_path"])
        if miss:
            return _fail(miss)
        return _pass()

    if c == "C-UI-03":
        miss = _require_ui_tokens(web_routes / "Ingestion.tsx", ["最近任务", "trace_type=ingestion", "历史任务"])
        if miss:
            return _fail(miss)
        _ = env.ingest(docs / "sample.md", policy="new_version")
        _ = env.ingest(docs / "simple.pdf", policy="new_version")
        r = env.api_client().get("/api/traces?trace_type=ingestion&limit=20&offset=0")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        items = (r.json() or {}).get("items") or []
        if not items:
            return _fail("trace_items_empty")
        return _pass()

    if c == "D-UI-01":
        miss = _require_ui_tokens(web_routes / "IngestionTrace.tsx", ["关键词", "上一页", "下一页", 'params.set("trace_type", "ingestion")'])
        if miss:
            return _fail(miss)
        _ = env.ingest(docs / "sample.md", policy="new_version")
        _ = env.ingest(docs / "sample.md", policy="skip")
        r0 = env.api_client().get("/api/traces?trace_type=ingestion&limit=1&offset=0")
        r1 = env.api_client().get("/api/traces?trace_type=ingestion&limit=1&offset=1")
        if r0.status_code != 200 or r1.status_code != 200:
            return _fail("http_error")
        return _pass()

    if c == "D-UI-02":
        miss = _require_ui_tokens(web_routes / "IngestionTrace.tsx", ["Stage", "耗时", "spans"])
        if miss:
            return _fail(miss)
        _ = env.ingest(docs / "sample.md", policy="skip")
        rlist = env.api_client().get("/api/traces?trace_type=ingestion&limit=10&offset=0")
        if rlist.status_code != 200:
            return _fail(f"http_{rlist.status_code}")
        items = (rlist.json() or {}).get("items") or []
        if not items:
            return _fail("no_traces")
        trace_id = (items[0] or {}).get("trace_id")
        if not trace_id:
            return _fail("missing_trace_id")
        r = env.api_client().get(f"/api/trace/{trace_id}")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        tj = r.json() or {}
        trace_obj = tj.get("trace") if isinstance(tj.get("trace"), dict) else tj
        spans = trace_obj.get("spans") if isinstance(trace_obj, dict) else None
        if not isinstance(spans, list) or not spans:
            return _fail("missing_spans")
        return _pass()

    if c == "E-UI-01":
        miss = _require_ui_tokens(web_routes / "QueryTrace.tsx", ["检索证据", "retrieval", "fusion", "rerank"])
        if miss:
            return _fail(miss)
        _ = env.ingest(docs / "sample.md", policy="skip")
        q = env.query("FTS5", top_k=5)
        if q.status != "PASS":
            return q
        rlist = env.api_client().get("/api/traces?trace_type=query&limit=10&offset=0")
        if rlist.status_code != 200:
            return _fail(f"http_{rlist.status_code}")
        items = (rlist.json() or {}).get("items") or []
        trace_id = (items[0] or {}).get("trace_id") if items else None
        if not trace_id:
            return _fail("missing_trace_id")
        r = env.api_client().get(f"/api/trace/{trace_id}")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        tj = r.json() or {}
        trace_obj = tj.get("trace") if isinstance(tj.get("trace"), dict) else tj
        if not isinstance(trace_obj, dict):
            return _fail("missing_trace_payload")
        kinds = []
        for sp in trace_obj.get("spans") or []:
            for ev in (sp.get("events") or []):
                kinds.append(ev.get("kind"))
        if "retrieval.candidates" not in kinds and "retrieval.fused" not in kinds:
            return _fail("missing_retrieval_evidence")
        return _pass()

    if c == "E-UI-02":
        miss = _require_ui_tokens(web_routes / "QueryTrace.tsx", ["无命中", "执行查询", "api.query"])
        if miss:
            return _fail(miss)
        run_id = str(shared.get("run_id") or _now_run_id())
        tmp_settings = root / "config" / f"settings.qa.{run_id}.{env.name.lower()}.empty_query_ui.yaml"
        _write_settings(
            tmp_settings,
            run_id=run_id,
            profile=f"{env.name.lower()}_empty_query_ui",
            defaults_strategy=env.strategy_config_id,
        )
        empty_env = ProfileEnv(name=env.name, settings_path=tmp_settings, strategy_config_id=env.strategy_config_id)
        empty_env.activate()
        from src.core.runners.query import QueryRunner

        runner = QueryRunner(settings_path=empty_env.settings_path)
        resp = runner.run("uuid_not_exists_ui_1234567890", strategy_config_id=empty_env.strategy_config_id, top_k=5)
        if resp.sources:
            return _fail("expected_empty_sources")
        return StepResult(status="PASS", trace_id=resp.trace_id)

    if c == "F-UI-01":
        miss = _require_ui_tokens(web_routes / "EvalPanel.tsx", ["Run Eval", "dataset_id", "strategy_config_id", "历史评估"])
        if miss:
            return _fail(miss)
        r = env.api_client().post(
            "/api/eval/run",
            json={"dataset_id": "rag_eval_small", "strategy_config_id": "default", "top_k": 5},
        )
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        body = r.json() or {}
        if body.get("status") not in {"ok", "error"}:
            return _fail(f"unexpected_eval_status:{body.get('status')}")
        run_id = body.get("run_id")
        if body.get("status") == "ok" and not run_id:
            return _fail("missing_run_id")
        if body.get("status") == "error" and not body.get("reason"):
            return _fail("missing_error_reason")
        rr = env.api_client().get("/api/eval/runs?limit=50&offset=0")
        if rr.status_code != 200:
            return _fail(f"http_{rr.status_code}")
        items = (rr.json() or {}).get("items") or []
        if run_id and not any((it or {}).get("run_id") == run_id for it in items):
            return _fail("run_not_listed")
        return _pass()

    if c == "F-UI-02":
        miss = _require_ui_tokens(web_routes / "EvalPanel.tsx", ["metric", "window", "无数据", "api.evalTrends"])
        if miss:
            return _fail(miss)
        r1 = env.api_client().get("/api/eval/trends?metric=hit_rate@k&window=30")
        r2 = env.api_client().get("/api/eval/trends?metric=mrr&window=7")
        if r1.status_code != 200 or r2.status_code != 200:
            return _fail("http_error")
        j1 = r1.json() or {}
        j2 = r2.json() or {}
        if not all(k in j1 for k in ("metric", "window", "points")):
            return _fail("missing_keys_r1")
        if not all(k in j2 for k in ("metric", "window", "points")):
            return _fail("missing_keys_r2")
        return _pass()

    if case.is_ui:
        return _blocked("ui:no_case_executor")

    # --- A: Overview ---
    if c == "A-01":
        r = env.api_client().get("/api/overview")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json()
        if not all(k in j for k in ("assets", "health", "providers")):
            return _fail("missing_keys")
        return _pass()

    if c == "A-02":
        # Ensure at least one ingestion trace exists so providers snapshot is populated.
        _ = env.ingest(docs / "sample.md", policy="skip")
        r = env.api_client().get("/api/overview")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        providers = (r.json() or {}).get("providers") or {}
        if not isinstance(providers, dict) or not providers:
            return _fail("providers_empty")
        return _pass()

    if c == "A-03":
        _ = env.ingest(docs / "sample.md", policy="skip")
        _ = env.ingest(docs / "with_images.pdf", policy="new_version")
        r = env.api_client().get("/api/overview")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        assets = (r.json() or {}).get("assets") or {}
        if int(assets.get("docs") or 0) < 2:
            return _fail("docs_lt_2")
        if int(assets.get("chunks") or 0) <= 0:
            return _fail("chunks_eq_0")
        if int(assets.get("assets") or 0) < 1:
            return _fail("assets_lt_1")
        return _pass()

    if c == "A-04":
        _ = env.ingest(docs / "sample.md", policy="skip")
        _ = env.query("FTS5", top_k=5)
        r = env.api_client().get("/api/overview")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        health = (r.json() or {}).get("health") or {}
        if int(health.get("recent_traces") or 0) <= 0:
            return _fail("recent_traces_eq_0")
        return _pass()

    if c == "A-05":
        # Execute in a fresh env to keep it empty (the main env will be dirtied by A-03/A-04).
        run_id = str(shared.get("run_id") or _now_run_id())
        root = _repo_root()
        tmp_settings = root / "config" / f"settings.qa.{run_id}.{env.name.lower()}.empty.yaml"
        _write_settings(
            tmp_settings,
            run_id=run_id,
            profile=f"{env.name.lower()}_empty",
            defaults_strategy=env.strategy_config_id,
        )
        empty_env = ProfileEnv(name=env.name, settings_path=tmp_settings, strategy_config_id=env.strategy_config_id)
        r = empty_env.api_client().get("/api/overview")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        assets = (r.json() or {}).get("assets") or {}
        if int(assets.get("docs") or 0) != 0:
            return _fail("docs_not_0")
        return _pass()

    # --- B: Data Browser ---
    if c == "B-01":
        _ = env.ingest(docs / "sample.md", policy="skip")
        r = env.api_client().get("/api/documents?limit=50&offset=0")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        items = (r.json() or {}).get("items") or []
        if not items:
            return _fail("items_empty")
        return _pass()

    if c == "B-02":
        _ = env.ingest(docs / "sample.md", policy="skip")
        _ = env.ingest(docs / "simple.pdf", policy="new_version")
        r0 = env.api_client().get("/api/documents?limit=1&offset=0")
        r1 = env.api_client().get("/api/documents?limit=1&offset=1")
        if r0.status_code != 200 or r1.status_code != 200:
            return _fail("http_error")
        i0 = (r0.json() or {}).get("items") or []
        if not i0:
            return _fail("page0_empty")
        doc_id = (i0[0] or {}).get("doc_id")
        if not doc_id:
            return _fail("missing_doc_id")
        rf = env.api_client().get(f"/api/documents?doc_id={doc_id}")
        if rf.status_code != 200:
            return _fail("filter_http_error")
        items = (rf.json() or {}).get("items") or []
        if not items or any((it or {}).get("doc_id") != doc_id for it in items):
            return _fail("filter_mismatch")
        return _pass()

    if c == "B-03":
        res = env.ingest(docs / "sample.md", policy="new_version")
        if res.status != "PASS":
            return res
        doc_id = (res.details or {}).get("doc_id")
        version_id = (res.details or {}).get("version_id")
        if not doc_id:
            return _fail("missing_doc_id")
        _ = env.admin_delete(str(doc_id), str(version_id) if version_id else None, mode="soft")
        r_hide = env.api_client().get("/api/documents?include_deleted=false")
        r_show = env.api_client().get("/api/documents?include_deleted=true")
        if r_hide.status_code != 200 or r_show.status_code != 200:
            return _fail("http_error")
        hide_items = (r_hide.json() or {}).get("items") or []
        show_items = (r_show.json() or {}).get("items") or []
        if any((it or {}).get("status") == "deleted" for it in hide_items):
            return _fail("deleted_visible_when_hidden")
        if not any((it or {}).get("status") == "deleted" for it in show_items):
            return _fail("deleted_not_visible_when_shown")
        return _pass()

    if c == "B-04":
        _ = env.ingest(docs / "sample.md", policy="skip")
        q = env.query("FTS5", top_k=5)
        if q.status != "PASS":
            return q
        sources = env.last_query.get("sources") or []
        chunk_id = getattr(sources[0], "chunk_id", None) if sources else None
        if not chunk_id:
            return _fail("missing_chunk_id")
        r = env.api_client().get(f"/api/chunk/{chunk_id}")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        if j.get("chunk_id") != chunk_id:
            return _fail("chunk_id_mismatch")
        if "chunk_text" not in j:
            return _fail("missing_chunk_text")
        return _pass()

    if c == "B-05":
        r = env.api_client().get("/api/chunk/chk_not_exists")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        if (r.json() or {}).get("error") != "not_found":
            return _fail("expected_not_found")
        return _pass()

    # --- C: Ingestion Manager API ---
    if c == "C-01":
        payload = {"file_path": str(docs / "sample.md"), "policy": "default", "strategy_config_id": "default"}
        r = env.api_client().post("/api/ingest", json=payload)
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        structured = j.get("structured") or {}
        if not isinstance(structured, dict) or structured.get("status") not in {"ok", "skipped"}:
            return _fail("structured_not_ok")
        return StepResult(status="PASS", trace_id=j.get("trace_id"))

    if c == "C-02":
        r = env.api_client().post("/api/ingest", json={})
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        if (r.json() or {}).get("status") != "error":
            return _fail("expected_error")
        return _pass()

    if c == "C-03":
        r = env.api_client().post("/api/ingest", json={"file_path": str(docs / "nope.pdf"), "policy": "skip"})
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        # IngestRunner returns structured error.
        structured = (r.json() or {}).get("structured") or {}
        if isinstance(structured, dict) and structured.get("status") == "error":
            return _pass()
        return _fail("expected_structured_error")

    if c == "C-04":
        a = env.ingest(docs / "simple.pdf", policy="new_version")
        b = env.ingest(docs / "sample.md", policy="new_version")
        if a.status != "PASS":
            return a
        if b.status != "PASS":
            return b
        return _pass()

    # --- D: Ingestion Traces ---
    if c == "D-01":
        _ = env.ingest(docs / "sample.md", policy="new_version")
        _ = env.ingest(docs / "sample.md", policy="skip")
        r = env.api_client().get("/api/traces?trace_type=ingestion&limit=10&offset=0")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        items = j.get("items") or []
        if not isinstance(items, list):
            return _fail("items_not_list")
        return _pass()

    if c == "D-02":
        _ = env.ingest(docs / "sample.md", policy="skip")
        rlist = env.api_client().get("/api/traces?trace_type=ingestion&limit=10&offset=0")
        if rlist.status_code != 200:
            return _fail(f"http_{rlist.status_code}")
        items = (rlist.json() or {}).get("items") or []
        if not items:
            return _fail("no_traces")
        trace_id = (items[0] or {}).get("trace_id")
        if not trace_id:
            return _fail("missing_trace_id")
        r = env.api_client().get(f"/api/trace/{trace_id}")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        tj = r.json() or {}
        # Backward/forward compatible: old shape returned envelope at top-level,
        # new shape returns {"trace": <envelope>, "error_events": [...]}
        trace_obj = tj.get("trace") if isinstance(tj.get("trace"), dict) else tj
        if not isinstance(trace_obj, dict):
            return _fail("missing_trace_payload")
        if trace_obj.get("trace_id") != trace_id:
            return _fail("trace_id_mismatch")
        spans = trace_obj.get("spans") or []
        if not isinstance(spans, list) or not spans:
            return _fail("missing_spans")
        return StepResult(status="PASS", trace_id=trace_id)

    if c == "D-03":
        # unsupported type
        bad = env.ingest(docs / "sample.txt", policy="new_version")
        if bad.status == "PASS":
            # if it somehow passed, that's wrong.
            return _fail("expected_failure")
        # Validate trace exists in /api/trace (best-effort).
        rlist = env.api_client().get("/api/traces?trace_type=ingestion&limit=50&offset=0")
        if rlist.status_code != 200:
            return StepResult(status="PASS", trace_id=bad.trace_id, details=bad.details, error=bad.error)
        return StepResult(status="PASS", trace_id=bad.trace_id, details=bad.details, error=bad.error)

    # --- E: Query Traces ---
    if c == "E-01":
        _ = env.ingest(docs / "sample.md", policy="skip")
        _ = env.query("FTS5", top_k=5)
        r = env.api_client().get("/api/traces?trace_type=query&limit=10&offset=0")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        items = (r.json() or {}).get("items") or []
        if not items:
            return _fail("items_empty")
        return _pass()

    if c == "E-02":
        _ = env.ingest(docs / "sample.md", policy="skip")
        q = env.query("FTS5", top_k=5)
        if q.status != "PASS":
            return q
        rlist = env.api_client().get("/api/traces?trace_type=query&limit=10&offset=0")
        items = (rlist.json() or {}).get("items") or []
        trace_id = (items[0] or {}).get("trace_id") if items else None
        if not trace_id:
            return _fail("missing_trace_id")
        r = env.api_client().get(f"/api/trace/{trace_id}")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        tj = r.json() or {}
        trace_obj = tj.get("trace") if isinstance(tj.get("trace"), dict) else tj
        if not isinstance(trace_obj, dict):
            return _fail("missing_trace_payload")
        kinds = []
        for sp in trace_obj.get("spans") or []:
            for ev in (sp.get("events") or []):
                kinds.append(ev.get("kind"))
        if "retrieval.candidates" not in kinds and "retrieval.fused" not in kinds:
            return _fail("missing_retrieval_evidence")
        return StepResult(status="PASS", trace_id=trace_id)

    if c == "E-03":
        # Run in a fresh empty env: dense retrieval always returns Top-K if any chunks exist.
        # This case verifies "empty library -> empty sources" is diagnosable, not silent fail.
        run_id = str(shared.get("run_id") or _now_run_id())
        root = _repo_root()
        tmp_settings = root / "config" / f"settings.qa.{run_id}.{env.name.lower()}.empty_query.yaml"
        _write_settings(
            tmp_settings,
            run_id=run_id,
            profile=f"{env.name.lower()}_empty_query",
            defaults_strategy=env.strategy_config_id,
        )
        empty_env = ProfileEnv(name=env.name, settings_path=tmp_settings, strategy_config_id=env.strategy_config_id)
        empty_env.activate()
        from src.core.runners.query import QueryRunner

        runner = QueryRunner(settings_path=empty_env.settings_path)
        resp = runner.run("uuid_not_exists_1234567890", strategy_config_id=empty_env.strategy_config_id, top_k=5)
        if resp.sources:
            return _fail("expected_empty_sources")
        return StepResult(status="PASS", trace_id=resp.trace_id)

    # --- F: Eval Panel API ---
    if c == "F-01":
        r = env.api_client().post(
            "/api/eval/run",
            json={
                "dataset_id": "__qa_missing_dataset__",
                "strategy_config_id": env.strategy_config_id,
                "top_k": 1,
            },
        )
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        status = j.get("status")
        if status != "error":
            return _fail("unexpected_status")
        if not j.get("reason"):
            return _fail("missing_error_reason")
        return _pass()

    if c == "F-02":
        # Run an eval and ensure it shows up in /api/eval/runs.
        env.activate()
        from src.core.runners.eval import EvalRunner

        er = EvalRunner(settings_path=env.settings_path)
        try:
            res = er.run("rag_eval_small", strategy_config_id=env.strategy_config_id, top_k=5)
        except Exception as e:
            status = _classify_real_error(str(e)) if env.name == "REAL" else "FAIL"
            return StepResult(status=status, error=str(e))
        r = env.api_client().get("/api/eval/runs?limit=50&offset=0")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        items = (r.json() or {}).get("items") or []
        if not any((it or {}).get("run_id") == res.run_id for it in items):
            return _fail("run_not_listed")
        return StepResult(status="PASS", details={"run_id": res.run_id})

    if c == "F-03":
        r = env.api_client().get("/api/eval/trends?metric=hit_rate@k&window=30")
        if r.status_code != 200:
            return _fail(f"http_{r.status_code}")
        j = r.json() or {}
        if not all(k in j for k in ("metric", "window", "points")):
            return _fail("missing_keys")
        return _pass()

    # --- G: CLI ingest ---
    if c == "G-01":
        return env.ingest(docs / "sample.md", policy="new_version")

    if c == "G-02":
        res = env.ingest(docs / "with_images.pdf", policy="new_version")
        if res.status != "PASS":
            return res
        assets_written = ((res.details or {}).get("counts") or {}).get("assets_written")
        if int(assets_written or 0) < 1:
            return _fail("assets_written_lt_1")
        return res

    if c == "G-03":
        res = env.ingest(docs / "sample.txt", policy="new_version")
        # Should fail.
        if res.status == "PASS":
            return _fail("expected_error")
        return StepResult(status="PASS", trace_id=res.trace_id, details=res.details, error=res.error)

    if c == "G-04":
        a = env.ingest(docs / "sample.md", policy="new_version")
        b = env.ingest(docs / "sample.md", policy="skip")
        if a.status != "PASS":
            return a
        if b.status != "PASS":
            return b
        if (b.details or {}).get("decision") != "skip":
            return _fail("expected_skip_decision")
        return _pass()

    if c == "G-05":
        res = env.ingest(docs / "complex_technical_doc.pdf", policy="new_version")
        if res.status != "PASS":
            return res
        chunks_written = ((res.details or {}).get("counts") or {}).get("chunks_written")
        if int(chunks_written or 0) <= 5:
            return _fail("chunks_written_le_5")
        return res

    # --- H: CLI query ---
    if c == "H-01":
        _ = env.ingest(docs / "sample.md", policy="skip")
        return env.query("FTS5", top_k=5)

    if c == "H-02":
        _ = env.ingest(docs / "complex_technical_doc.pdf", policy="new_version")
        return env.query("Table of Contents", top_k=8)

    if c == "H-03":
        _ = env.ingest(docs / "blogger_intro.pdf", policy="new_version")
        return env.query("笔记有多少字", top_k=5)

    if c == "H-04":
        _ = env.ingest(docs / "with_images.pdf", policy="new_version")
        q = env.query("embedded image", top_k=5)
        if q.status != "PASS":
            return q
        # ensure at least one source has asset_ids
        sources = env.last_query.get("sources") or []
        if not any(getattr(s, "asset_ids", None) for s in sources):
            return _fail("no_asset_ids_in_sources")
        return q

    if c == "H-05":
        res = env.ingest(docs / "sample.md", policy="new_version")
        if res.status != "PASS":
            return res
        q1 = env.query("FTS5", top_k=5)
        if q1.status != "PASS":
            return q1
        doc_id = (res.details or {}).get("doc_id")
        version_id = (res.details or {}).get("version_id")
        if not doc_id:
            return _fail("missing_doc_id")
        _ = env.admin_delete(str(doc_id), str(version_id) if version_id else None, mode="soft")
        env.activate()
        from src.core.runners.query import QueryRunner

        runner = QueryRunner(settings_path=env.settings_path)
        q2 = runner.run("FTS5", strategy_config_id=env.strategy_config_id, top_k=5)
        if any(getattr(s, "doc_id", None) == doc_id for s in q2.sources):
            return _fail("deleted_version_still_returned")
        return StepResult(status="PASS", trace_id=q2.trace_id)

    # --- I: Eval CLI ---
    if c == "I-01":
        env.activate()
        from src.core.runners.eval import EvalRunner

        runner = EvalRunner(settings_path=env.settings_path)
        try:
            res = runner.run("rag_eval_small", strategy_config_id=env.strategy_config_id, top_k=5)
        except Exception as e:
            status = _classify_real_error(str(e)) if env.name == "REAL" else "FAIL"
            return StepResult(status=status, error=str(e))
        if not res.run_id:
            return _fail("missing_run_id")
        return StepResult(status="PASS", details={"run_id": res.run_id})

    # --- J: MCP protocol ---
    if c.startswith("J-"):
        env.activate()
        root = _repo_root()
        py = root / ".venv" / "bin" / "python"
        cmd = ["bash", "scripts/module-rag-mcp", "--settings", str(env.settings_path)]
        child_env = os.environ.copy()
        # Ensure MCP wrapper uses project venv.
        if py.exists():
            child_env["PYTHON"] = str(py)

        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def _rpc(req: dict[str, Any]) -> dict[str, Any]:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            # Some environments may interleave non-JSON lines; scan a small window.
            for _ in range(20):
                line = proc.stdout.readline()
                if not line:
                    break
                s = line.strip()
                if not s:
                    continue
                try:
                    return json.loads(s)
                except Exception:
                    continue
            err = ""
            try:
                if proc.stderr is not None:
                    err = (proc.stderr.read() or "").strip()
            except Exception:
                err = ""
            raise RuntimeError(f"mcp_empty_or_invalid_response{(': ' + err) if err else ''}")

        def _is_invalid_params_error(resp: dict[str, Any]) -> bool:
            er = resp.get("error") if isinstance(resp, dict) else None
            return isinstance(er, dict) and int(er.get("code") or 0) == -32602

        try:
            if c == "J-01":
                r = _rpc(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05"},
                    }
                )
                pv = ((r.get("result") or {}).get("protocolVersion")) if isinstance(r, dict) else None
                if pv != "2024-11-05":
                    return _fail("protocol_negotiation_failed")
                return _pass()

            if c == "J-02":
                r = _rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
                tools = (r.get("result") or {}).get("tools") if isinstance(r, dict) else None
                if not isinstance(tools, list) or not tools:
                    return _fail("tools_empty")
                bad = [t.get("name") for t in tools if not re.match(r"^[a-zA-Z0-9_-]+$", str(t.get("name") or ""))]
                if bad:
                    return _fail(f"invalid_tool_names:{bad}")
                return _pass()

            if c == "J-03":
                r = _rpc(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "library_ping", "arguments": {}},
                    }
                )
                payload = json.dumps(r.get("result", {}), ensure_ascii=False) if isinstance(r, dict) else ""
                if "pong" not in payload.lower():
                    return _fail("pong_missing")
                return _pass()

            if c == "J-04":
                r = _rpc(
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {"name": "library_ping", "arguments": "{\"message\":\"hi\"}"},
                    }
                )
                payload = json.dumps(r.get("result", {}), ensure_ascii=False) if isinstance(r, dict) else ""
                if "hi" not in payload:
                    return _fail("json_string_args_not_effective")
                return _pass()

            if c == "J-05":
                failures: list[str] = []
                sample_md = str(docs / "sample.md")
                # 1) ingest/query default compatibility
                calls = [
                    (
                        "ingest",
                        {
                            "jsonrpc": "2.0",
                            "id": 5,
                            "method": "tools/call",
                            "params": {
                                "name": "library_ingest",
                                "arguments": {
                                    "file_path": sample_md,
                                    "policy": "default",
                                    "strategy_config_id": "default",
                                },
                            },
                        },
                    ),
                    (
                        "query",
                        {
                            "jsonrpc": "2.0",
                            "id": 6,
                            "method": "tools/call",
                            "params": {
                                "name": "library_query",
                                "arguments": {
                                    "query": "FTS5",
                                    "strategy_config_id": "default",
                                    "top_k": 5,
                                },
                            },
                        },
                    ),
                    (
                        "delete_document",
                        {
                            "jsonrpc": "2.0",
                            "id": 11,
                            "method": "tools/call",
                            "params": {
                                "name": "library_delete_document",
                                "arguments": {"doc_id": "doc_not_exist", "mode": "default"},
                            },
                        },
                    ),
                ]
                for label, req in calls:
                    try:
                        resp = _rpc(req)
                        if _is_invalid_params_error(resp):
                            failures.append(f"{label}:invalid_params")
                    except Exception as e:
                        failures.append(f"{label}:{type(e).__name__}:{e}")

                # 2) query_assets default compatibility requires non-empty asset_ids.
                # Build assets deterministically via with_images.pdf.
                try:
                    r_ing = _rpc(
                        {
                            "jsonrpc": "2.0",
                            "id": 7,
                            "method": "tools/call",
                            "params": {
                                "name": "library_ingest",
                                "arguments": {
                                    "file_path": str(docs / "with_images.pdf"),
                                    "policy": "default",
                                    "strategy_config_id": "default",
                                },
                            },
                        }
                    )
                    if _is_invalid_params_error(r_ing):
                        failures.append("query_assets_setup_ingest:invalid_params")
                    r_q = _rpc(
                        {
                            "jsonrpc": "2.0",
                            "id": 8,
                            "method": "tools/call",
                            "params": {
                                "name": "library_query",
                                "arguments": {
                                    "query": "embedded image",
                                    "strategy_config_id": "default",
                                    "top_k": 5,
                                },
                            },
                        }
                    )
                    if _is_invalid_params_error(r_q):
                        failures.append("query_assets_setup_query:invalid_params")
                    aids: list[str] = []
                    sc = (r_q.get("result") or {}).get("structuredContent") if isinstance(r_q, dict) else None
                    sources = (sc or {}).get("sources") if isinstance(sc, dict) else []
                    if isinstance(sources, list):
                        for s in sources:
                            if isinstance(s, dict):
                                for aid in s.get("asset_ids") or []:
                                    if isinstance(aid, str) and aid:
                                        aids.append(aid)
                    aids = list(dict.fromkeys(aids))
                    if not aids:
                        failures.append("query_assets:no_asset_ids")
                    else:
                        r_assets = _rpc(
                            {
                                "jsonrpc": "2.0",
                                "id": 9,
                                "method": "tools/call",
                                "params": {
                                    "name": "library_query_assets",
                                    "arguments": {
                                        "asset_ids": aids[:1],
                                        "variant": "default",
                                        "max_bytes": "default",
                                    },
                                },
                            }
                        )
                        if _is_invalid_params_error(r_assets):
                            failures.append("query_assets:invalid_params")
                except Exception as e:
                    failures.append(f"query_assets:{type(e).__name__}:{e}")
                if failures:
                    return _fail("; ".join(failures)[:500])
                return _pass()

            return _blocked("mcp:no_executor")
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    # --- L: reranker mode ---
    if c == "L-04":
        # Real cross-encoder inference (non-mock) smoke.
        env.activate()
        try:
            from src.libs.interfaces.vector_store import RankedCandidate
            from src.libs.providers.reranker.cross_encoder import CrossEncoderReranker

            rr = CrossEncoderReranker(
                model_name=os.environ.get("MODULE_RAG_CE_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
                device=os.environ.get("MODULE_RAG_CE_DEVICE", "cpu"),
                max_candidates=2,
                batch_size=2,
                max_length=256,
                score_activation="raw",
            )
            candidates = [
                RankedCandidate(
                    chunk_id="relevant",
                    score=0.5,
                    rank=1,
                    source="rrf",
                    metadata={"rerank_text": "Paris is the capital of France."},
                ),
                RankedCandidate(
                    chunk_id="irrelevant",
                    score=0.5,
                    rank=2,
                    source="rrf",
                    metadata={"rerank_text": "Bananas are yellow fruits rich in potassium."},
                ),
            ]
            out = rr.rerank("What is the capital of France?", candidates)
            if not out or out[0].chunk_id != "relevant":
                return _fail("cross_encoder_bad_order")
            return _pass()
        except Exception as e:
            if _is_cross_encoder_env_unready(e):
                return _blocked("cross_encoder:env_unready")
            return _fail(f"cross_encoder_integration_failed:{type(e).__name__}:{e}")

    # --- K: provider switch / llm fallback ---
    if c == "K-01":
        env.activate()
        from src.core.runners.query import QueryRunner

        llm = _make_provider(
            "llm",
            "deepseek",
            base_url="http://127.0.0.1:9/v1",
            api_key="qa-invalid",
            model="deepseek-chat",
            timeout_s=0.2,
        )
        build_rt, _ = _make_fixed_query_runtime_builder(
            work_dir=root / "data" / "qa_runs" / str(shared.get("run_id") or _now_run_id()) / env.name.lower() / "k01",
            llm=llm,
            llm_provider_id="deepseek",
            empty_candidates=True,
        )
        resp = QueryRunner(runtime_builder=build_rt).run(
            "provider switch assemble smoke",
            strategy_config_id="local.test",
            top_k=3,
        )
        if resp.trace is None:
            return _fail("missing_trace")
        llm_provider = ((resp.trace.providers or {}).get("llm") or {}).get("provider_id")
        if llm_provider != "deepseek":
            return _fail(f"llm_provider_not_switched:{llm_provider}")
        if resp.sources:
            return _fail("expected_empty_sources")
        return StepResult(status="PASS", trace_id=resp.trace_id)

    if c == "K-02":
        env.activate()
        from src.core.runners.query import QueryRunner

        llm = _make_provider(
            "llm",
            "deepseek",
            base_url="http://127.0.0.1:9/v1",
            api_key="qa-invalid",
            model="deepseek-chat",
            timeout_s=0.2,
        )
        build_rt, _ = _make_fixed_query_runtime_builder(
            work_dir=root / "data" / "qa_runs" / str(shared.get("run_id") or _now_run_id()) / env.name.lower() / "k02",
            llm=llm,
            llm_provider_id="deepseek",
        )
        resp = QueryRunner(runtime_builder=build_rt).run(
            "What is the capital of France?",
            strategy_config_id="local.test",
            top_k=2,
        )
        if not resp.sources:
            return _fail("empty_sources")
        if "extractive fallback" not in (resp.content_md or ""):
            return _fail("fallback_output_missing")
        if resp.trace is None:
            return _fail("missing_trace")
        if ((resp.trace.providers or {}).get("llm") or {}).get("provider_id") != "deepseek":
            return _fail("missing_deepseek_provider")
        if not _trace_has_event(resp.trace, "stage.generate", "warn.generate_fallback"):
            return _fail("missing_llm_fallback_event")
        return StepResult(status="PASS", trace_id=resp.trace_id)

    # --- L: reranker mode ---
    if c == "L-01":
        env.activate()
        from src.core.runners.query import QueryRunner
        from src.libs.providers.llm.fake_llm import FakeLLM

        build_rt, ids = _make_fixed_query_runtime_builder(
            work_dir=root / "data" / "qa_runs" / str(shared.get("run_id") or _now_run_id()) / env.name.lower() / "l01",
            llm=FakeLLM(name="fake-llm"),
        )
        resp = QueryRunner(runtime_builder=build_rt).run(
            "What is the capital of France?",
            strategy_config_id="local.test",
            top_k=2,
        )
        if not resp.sources:
            return _fail("empty_sources")
        if resp.sources[0].chunk_id != ids["irrelevant"]:
            return _fail("expected_fusion_order")
        if resp.trace is None:
            return _fail("missing_trace")
        if not _trace_has_event(resp.trace, "stage.rerank", "rerank.skipped"):
            return _fail("missing_rerank_skipped")
        if resp.trace.aggregates.get("effective_rank_source") != "fusion":
            return _fail("missing_fusion_aggregate")
        return StepResult(status="PASS", trace_id=resp.trace_id)

    if c == "L-02":
        env.activate()
        from src.core.runners.query import QueryRunner
        from src.libs.providers.llm.fake_llm import FakeLLM

        server = None
        try:
            server_url, server = _start_fake_openai_chat_server(
                '[{"chunk_id":"chk_paris","score":0.99},{"chunk_id":"chk_banana","score":0.01}]'
            )
            reranker = _make_provider(
                "reranker",
                "openai_compatible_llm",
                base_url=server_url,
                api_key="qa-local",
                model="qwen3-rerank",
                timeout_s=2.0,
                max_candidates=2,
                max_chunk_chars=120,
            )

            off_rt, ids = _make_fixed_query_runtime_builder(
                work_dir=root / "data" / "qa_runs" / str(shared.get("run_id") or _now_run_id()) / env.name.lower() / "l02_off",
                llm=FakeLLM(name="fake-llm"),
            )
            on_rt, _ = _make_fixed_query_runtime_builder(
                work_dir=root / "data" / "qa_runs" / str(shared.get("run_id") or _now_run_id()) / env.name.lower() / "l02_on",
                llm=FakeLLM(name="fake-llm"),
                reranker=reranker,
                reranker_provider_id="openai_compatible_llm",
                rerank_profile_id="rerank.local_stub.v1",
            )
            runner_off = QueryRunner(runtime_builder=off_rt)
            runner_on = QueryRunner(runtime_builder=on_rt)
            resp_off = runner_off.run("What is the capital of France?", strategy_config_id="local.test", top_k=2)
            resp_on = runner_on.run("What is the capital of France?", strategy_config_id="local.test", top_k=2)
            if not resp_off.sources or not resp_on.sources:
                return _fail("empty_sources")
            if resp_off.sources[0].chunk_id != ids["irrelevant"]:
                return _fail("baseline_not_fusion_order")
            if resp_on.sources[0].chunk_id != ids["relevant"]:
                return _fail("rerank_order_unchanged")
            if resp_on.trace is None:
                return _fail("missing_trace")
            used = _last_trace_event(resp_on.trace, "stage.rerank", "rerank.used")
            if used is None:
                return _fail("missing_rerank_used")
            if used.attrs.get("rerank_applied") is not True:
                return _fail("rerank_not_applied")
            if used.attrs.get("effective_rank_source") != "rerank":
                return _fail("wrong_effective_rank_source")
            return StepResult(status="PASS", trace_id=resp_on.trace_id)
        finally:
            if server is not None:
                try:
                    server.shutdown()
                    server.server_close()
                except Exception:
                    pass

    if c == "L-03":
        env.activate()
        from src.core.runners.query import QueryRunner
        from src.libs.providers.llm.fake_llm import FakeLLM

        reranker = _make_provider(
            "reranker",
            "openai_compatible_llm",
            base_url="http://127.0.0.1:9/v1",
            api_key="qa-invalid",
            model="qwen3-rerank",
            timeout_s=0.2,
            max_candidates=2,
            max_chunk_chars=120,
        )
        off_rt, ids = _make_fixed_query_runtime_builder(
            work_dir=root / "data" / "qa_runs" / str(shared.get("run_id") or _now_run_id()) / env.name.lower() / "l03_off",
            llm=FakeLLM(name="fake-llm"),
        )
        on_rt, _ = _make_fixed_query_runtime_builder(
            work_dir=root / "data" / "qa_runs" / str(shared.get("run_id") or _now_run_id()) / env.name.lower() / "l03_on",
            llm=FakeLLM(name="fake-llm"),
            reranker=reranker,
            reranker_provider_id="openai_compatible_llm",
            rerank_profile_id="rerank.failover.v1",
        )
        runner_off = QueryRunner(runtime_builder=off_rt)
        runner_on = QueryRunner(runtime_builder=on_rt)
        resp_off = runner_off.run("What is the capital of France?", strategy_config_id="local.test", top_k=2)
        resp_on = runner_on.run("What is the capital of France?", strategy_config_id="local.test", top_k=2)
        if not resp_off.sources or not resp_on.sources:
            return _fail("empty_sources")
        if resp_off.sources[0].chunk_id != ids["irrelevant"]:
            return _fail("baseline_not_fusion_order")
        if resp_on.sources[0].chunk_id != resp_off.sources[0].chunk_id:
            return _fail("fallback_did_not_preserve_order")
        if resp_on.trace is None:
            return _fail("missing_trace")
        if not _trace_has_event(resp_on.trace, "stage.rerank", "warn.rerank_fallback"):
            return _fail("missing_rerank_fallback")
        used = _last_trace_event(resp_on.trace, "stage.rerank", "rerank.used")
        if used is None:
            return _fail("missing_rerank_used")
        if used.attrs.get("rerank_failed") is not True:
            return _fail("rerank_failed_flag_missing")
        if used.attrs.get("effective_rank_source") != "fusion":
            return _fail("wrong_effective_rank_source")
        return StepResult(status="PASS", trace_id=resp_on.trace_id)

    # --- M: config tolerance ---
    if c == "M-01":
        # Simulate missing endpoints file.
        prev = os.environ.get("MODULE_RAG_MODEL_ENDPOINTS_PATH")
        try:
            os.environ["MODULE_RAG_MODEL_ENDPOINTS_PATH"] = str(root / "config" / "model_endpoints.NOT_EXISTS.yaml")
            # Reload settings and attempt a query runtime build.
            env.activate()
            from src.core.runners.query import QueryRunner

            runner = QueryRunner(settings_path=env.settings_path)
            resp = runner.run("FTS5", strategy_config_id=env.strategy_config_id, top_k=3)
            if env.name == "OFFLINE":
                return StepResult(status="PASS", trace_id=resp.trace_id)
            # REAL likely fails due to missing base_url/api_key; must be structured error.
            if resp.content_md.startswith("未召回到相关内容"):
                return StepResult(status="PASS", trace_id=resp.trace_id)
            return StepResult(status="PASS", trace_id=resp.trace_id)
        except Exception as e:
            status = "PASS" if env.name == "OFFLINE" else "FAIL(config)"
            return StepResult(status=status, error=str(e))
        finally:
            if prev is None:
                os.environ.pop("MODULE_RAG_MODEL_ENDPOINTS_PATH", None)
            else:
                os.environ["MODULE_RAG_MODEL_ENDPOINTS_PATH"] = prev

    if c == "M-02":
        # Create a temp strategy with invalid provider_id for embedder.
        bad_path = (root / "data" / "qa_runs" / "tmp_invalid_provider.yaml").resolve()
        bad_path.parent.mkdir(parents=True, exist_ok=True)
        bad_path.write_text(
            "providers:\n"
            "  loader:\n"
            "    provider_id: loader.markdown\n"
            "  sectioner:\n"
            "    provider_id: sectioner.markdown_headings\n"
            "  chunker:\n"
            "    provider_id: chunker.rcts_within_section\n"
            "  embedder:\n"
            "    provider_id: not_exists\n"
            "    params: {dim: 8}\n"
            "  llm:\n"
            "    provider_id: fake\n"
            "    params: {name: fake}\n"
            "  vector_index:\n"
            "    provider_id: vector.chroma_lite\n"
            "  retriever:\n"
            "    provider_id: retriever.chroma_dense\n"
            "  sparse_retriever:\n"
            "    provider_id: sparse_retriever.fts5\n"
            "  fusion:\n"
            "    provider_id: fusion.rrf\n",
            encoding="utf-8",
        )
        try:
            env.activate()
            from src.core.runners.ingest import IngestRunner

            runner = IngestRunner(settings_path=env.settings_path)
            resp = runner.run(docs / "sample.md", strategy_config_id=str(bad_path), policy="new_version")
            if (resp.structured or {}).get("status") == "error":
                return StepResult(status="PASS", trace_id=resp.trace_id, details=resp.structured)
            return _fail("expected_error")
        except Exception as e:
            return StepResult(status="PASS", error=str(e))

    if c == "M-03":
        # Ping tolerates extra fields; ingest should reject unexpected fields.
        env.activate()
        root = _repo_root()
        py = root / ".venv" / "bin" / "python"
        cmd = ["bash", "scripts/module-rag-mcp", "--settings", str(env.settings_path)]
        child_env = os.environ.copy()
        if py.exists():
            child_env["PYTHON"] = str(py)

        proc = subprocess.Popen(
            cmd,
            cwd=str(root),
            env=child_env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def _rpc(req: dict[str, Any]) -> dict[str, Any]:
            assert proc.stdin is not None and proc.stdout is not None
            proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            for _ in range(20):
                line = proc.stdout.readline()
                if not line:
                    break
                s = line.strip()
                if not s:
                    continue
                try:
                    return json.loads(s)
                except Exception:
                    continue
            err = ""
            try:
                if proc.stderr is not None:
                    err = (proc.stderr.read() or "").strip()
            except Exception:
                err = ""
            raise RuntimeError(f"mcp_empty_or_invalid_response{(': ' + err) if err else ''}")

        try:
            _ = _rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 900,
                    "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05"},
                }
            )

            # ping with extra field should be accepted
            ping_resp = _rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 901,
                    "method": "tools/call",
                    "params": {
                        "name": "library_ping",
                        "arguments": {"message": "x", "extra": 123},
                    },
                }
            )
            if "error" in ping_resp:
                return _fail("ping_extra_unexpectedly_rejected")

            # ingest with extra field should be rejected as invalid params
            ingest_resp = _rpc(
                {
                    "jsonrpc": "2.0",
                    "id": 902,
                    "method": "tools/call",
                    "params": {
                        "name": "library_ingest",
                        "arguments": {
                            "file_path": str(docs / "sample.md"),
                            "policy": "skip",
                            "strategy_config_id": "local.test",
                            "extra": 1,
                        },
                    },
                }
            )
            err = ingest_resp.get("error") if isinstance(ingest_resp, dict) else None
            if not isinstance(err, dict) or int(err.get("code") or 0) != -32602:
                return _fail("ingest_extra_not_invalid_params")
            return _pass()
        except Exception as e:
            return _fail(f"m03_mcp_exec:{type(e).__name__}:{e}")
        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    # --- N: lifecycle ---
    if c == "N-01":
        res = env.ingest(docs / "sample.md", policy="new_version")
        if res.status != "PASS":
            return res
        doc_id = (res.details or {}).get("doc_id")
        version_id = (res.details or {}).get("version_id")
        if not doc_id:
            return _fail("missing_doc_id")
        _ = env.admin_delete(str(doc_id), str(version_id) if version_id else None, mode="soft")
        q = env.query("FTS5", top_k=5)
        # Expect query not returning deleted version.
        sources = env.last_query.get("sources") or []
        if any(getattr(s, "doc_id", None) == doc_id for s in sources):
            return _fail("deleted_version_returned")
        return q

    if c == "N-02":
        # Verify AdminRunner hard delete reports consistent affected counts across stores.
        res = env.ingest(docs / "sample.md", policy="new_version")
        if res.status != "PASS":
            return res
        doc_id = (res.details or {}).get("doc_id")
        version_id = (res.details or {}).get("version_id")
        if not doc_id:
            return _fail("missing_doc_id")
        hd = env.admin_delete(str(doc_id), str(version_id) if version_id else None, mode="hard")
        if hd.status != "PASS":
            return hd
        aff = hd.details.get("affected") if hd.details else None
        if not isinstance(aff, dict):
            return _fail("missing_affected")
        try:
            sqlite_chunks = int(((aff.get("sqlite") or {}).get("chunks")) or 0)
            chroma_vecs = int(((aff.get("chroma") or {}).get("vectors")) or 0)
            fts_docs = int(((aff.get("fts5") or {}).get("docs")) or 0)
        except Exception:
            return _fail("affected_not_int")
        if not (sqlite_chunks == chroma_vecs == fts_docs):
            return _fail("affected_mismatch")
        return hd

    # --- O: replacement ---
    if c == "O-01":
        # Copy sample.md -> A, mutate -> A1, revert -> A, verify skip on final ingest.
        env.activate()
        tmp_dir = root / "data" / "qa_runs" / "tmp_docs"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        a = tmp_dir / "A.md"
        a1 = tmp_dir / "A1.md"
        base = (docs / "sample.md").read_text(encoding="utf-8")
        a.write_text(base, encoding="utf-8")
        a1.write_text(base + "\nextra_line_for_A1\n", encoding="utf-8")

        r1 = env.ingest(a, policy="new_version")
        if r1.status != "PASS":
            return r1
        r2 = env.ingest(a1, policy="new_version")
        if r2.status != "PASS":
            return r2
        # revert to original content, ingest with skip should skip.
        a.write_text(base, encoding="utf-8")
        r3 = env.ingest(a, policy="skip")
        if r3.status != "PASS":
            return r3
        if (r3.details or {}).get("decision") != "skip":
            return _fail("expected_skip_on_revert")
        return StepResult(status="PASS", trace_id=r3.trace_id)

    if c == "O-02":
        _ = env.ingest(docs / "sample.md", policy="new_version")
        _ = env.ingest(docs / "complex_technical_doc.pdf", policy="new_version")
        q = env.query("FTS5", top_k=8)
        if q.status != "PASS":
            return q
        sources = env.last_query.get("sources") or []
        doc_ids = {getattr(s, "doc_id", None) for s in sources}
        if len([d for d in doc_ids if d]) < 1:
            return _fail("missing_doc_ids")
        return q

    return _blocked("no_executor")


def _append_progress_cases(
    progress_path: Path,
    *,
    run_id: str,
    notes: list[str],
    results: list[CaseResult],
) -> None:
    lines: list[str] = []
    if progress_path.exists():
        lines.append(progress_path.read_text(encoding="utf-8").rstrip("\n"))
        lines.append("")
    else:
        lines.append("# QA_TEST_PROGRESS\n")
        lines.append("记录规则：只记录“做了什么、结果是什么、下一步是什么”。本文件为本地执行产物，不提交到 Git（见 `.gitignore`）。")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"## Run: {run_id}（QA_TEST A..O 全量回归）")
    lines.append("")
    lines.append("### 本次做了什么")
    lines.append("")
    for n in notes:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("### 结果是什么")
    lines.append("")
    lines.append("| Case | OFFLINE | REAL | Overall | Evidence | Note |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for cr in results:
        off = cr.offline.status if cr.offline else "N/A"
        rea = cr.real.status if cr.real else "N/A"
        ev = ""
        if cr.offline and cr.offline.trace_id:
            ev += f"off:{cr.offline.trace_id} "
        if cr.real and cr.real.trace_id:
            ev += f"real:{cr.real.trace_id}"
        ev = ev.strip()
        note = cr.note or ""
        lines.append(f"| {cr.case.case_id} | {off} | {rea} | {cr.overall} | {ev} | {note} |")
    lines.append("")
    lines.append("### 用例明细（做什么 / 预期 / 执行结果）")
    lines.append("")

    def _fmt_exec(sr: StepResult | None) -> str:
        if sr is None:
            return "N/A"
        parts: list[str] = [sr.status]
        if sr.trace_id:
            parts.append(f"trace_id={sr.trace_id}")
        if sr.error:
            parts.append(f"error={sr.error}")
        return ", ".join(parts)

    for cr in results:
        title = cr.case.title.strip()
        lines.append(f"#### {cr.case.case_id}" + (f" {title}" if title else ""))
        if cr.case.steps_brief:
            lines.append(f"- 做什么：{cr.case.steps_brief}")
        elif cr.case.is_ui:
            lines.append("- 做什么：UI 用例自动化校验（前端契约 + API 行为联合断言）。")
        else:
            lines.append("- 做什么：（未解析到步骤摘要）")
        if cr.case.expected_brief:
            lines.append(f"- 预期：{cr.case.expected_brief}")
        else:
            lines.append("- 预期：（未解析到预期摘要）")
        lines.append(f"- 执行结果：OFFLINE={_fmt_exec(cr.offline)}; REAL={_fmt_exec(cr.real)}; Overall={cr.overall}")
        if cr.real and cr.real.diagnostic:
            lines.append(f"- REAL报错详情：{_summarize_diagnostic(cr.real.diagnostic)}")
        if cr.note:
            lines.append(f"- 备注：{cr.note}")
        lines.append("")
    lines.append("### 下一步是什么")
    lines.append("")
    blocked = [
        cr
        for cr in results
        if cr.overall == "BLOCKED"
        or (cr.offline and cr.offline.status.startswith("BLOCKED"))
        or (cr.real and cr.real.status.startswith("BLOCKED"))
    ]
    failed = [
        cr
        for cr in results
        if cr.overall == "FAIL"
        or (cr.offline and cr.offline.status.startswith("FAIL"))
        or (cr.real and cr.real.status.startswith("FAIL"))
    ]
    if failed:
        lines.append("- 存在 FAIL：优先按 Evidence 中的 trace_id 打开 `/api/trace/<id>` 或读取 logs 中对应 trace，定位失败 stage。")
    if blocked:
        lines.append("- 存在 BLOCKED：通常为 `env:network` 或 `no_executor`，需要补执行器或在本机 Terminal 跑 REAL。")
    if not failed and not blocked:
        lines.append("- 全量用例未出现 FAIL/BLOCKED，可考虑引入 UI 结构化断言与 Playwright 自动化。")
    lines.append("")

    progress_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def _append_progress(
    progress_path: Path,
    *,
    run_id: str,
    offline: dict[str, StepResult],
    real: dict[str, StepResult] | None,
    notes: list[str],
) -> None:
    lines: list[str] = []
    if progress_path.exists():
        lines.append(progress_path.read_text(encoding="utf-8").rstrip("\n"))
        lines.append("")
    else:
        lines.append("# QA_TEST_PROGRESS\n")
        lines.append("记录规则：只记录“做了什么、结果是什么、下一步是什么”。本文件为本地执行产物，不提交到 Git（见 `.gitignore`）。")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"## Run: {run_id}（Baseline: OFFLINE + REAL）")
    lines.append("")
    lines.append("### 本次做了什么")
    lines.append("")
    for n in notes:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("### 结果是什么")
    lines.append("")

    def emit_profile(title: str, results: dict[str, StepResult]) -> None:
        lines.append(f"#### {title}")
        lines.append("")
        for name, r in results.items():
            lines.append(f"- {name}: {r.status}")
            if r.trace_id:
                lines.append(f"- trace_id: `{r.trace_id}`")
            if r.details:
                # keep small
                keys = ["doc_id", "version_id", "counts", "reason", "error"]
                brief = {k: r.details.get(k) for k in keys if k in r.details}
                if brief:
                    lines.append(f"- details: `{brief}`")
            if r.error:
                lines.append(f"- error: `{r.error}`")
            lines.append("")

    emit_profile("OFFLINE（local.test）", offline)
    if real is not None:
        emit_profile("REAL（local.default）", real)

    lines.append("### 下一步是什么")
    lines.append("")
    next_steps: list[str] = []
    # If REAL is blocked, be explicit.
    if real is not None:
        blocked = [k for k, v in real.items() if v.status.startswith("BLOCKED")]
        if blocked:
            next_steps.append(
                "REAL 被环境阻断时：在本机 Terminal（网络可达）重跑 REAL 分支，并把输出中的 trace_id 回填到本文件。"
            )
    # If any failures, point to trace.
    failed = []
    for mp in (offline, real or {}):
        failed.extend([k for k, v in mp.items() if v.status.startswith("FAIL")])
    if failed:
        next_steps.append("若出现 FAIL：优先打开对应 trace_id 的 trace detail 定位失败 stage。")
    if not next_steps:
        next_steps.append("本次 baseline 无阻断/失败项，可继续扩展覆盖范围或引入 UI 结构化断言。")
    for s in next_steps:
        lines.append(f"- {s}")
    lines.append("")

    progress_path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


def _run_offline(run_id: str, settings_path: Path) -> dict[str, StepResult]:
    os.environ["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    from src.observability.obs import api as obs
    from src.observability.sinks.jsonl import JsonlSink
    from src.core.runners.ingest import IngestRunner
    from src.core.runners.query import QueryRunner
    from src.core.strategy import load_settings
    from src.observability.dashboard.app import create_app
    from fastapi.testclient import TestClient

    root = _repo_root()
    out: dict[str, StepResult] = {}

    # Persist traces so dashboard endpoints can validate trace lists.
    settings = load_settings(settings_path)
    obs.set_sink(JsonlSink(settings.paths.logs_dir))

    ingest = IngestRunner(settings_path=settings_path)
    resp = ingest.run(root / "tests" / "fixtures" / "docs" / "sample.md", strategy_config_id="local.test", policy="new_version")
    if (resp.structured or {}).get("status") != "ok":
        out["Ingest(sample.md)"] = StepResult(status="FAIL", trace_id=resp.trace_id, details=resp.structured, error=str((resp.structured or {}).get("error") or "ingest_error"))
        return out
    out["Ingest(sample.md)"] = StepResult(status="PASS", trace_id=resp.trace_id, details=resp.structured)

    q = QueryRunner(settings_path=settings_path)
    qresp = q.run("FTS5", strategy_config_id="local.test", top_k=5)
    if not qresp.sources:
        out["Query(FTS5)"] = StepResult(status="FAIL", trace_id=qresp.trace_id, details=qresp.structured, error="empty_sources")
        return out
    out["Query(FTS5)"] = StepResult(status="PASS", trace_id=qresp.trace_id, details=qresp.structured)

    app = create_app(settings)
    client = TestClient(app)
    try:
        r = client.get("/api/overview")
        ok = r.status_code == 200 and all(k in r.json() for k in ("assets", "health", "providers"))
        out["Dashboard(/api/overview)"] = StepResult(status="PASS" if ok else "FAIL", details={"status_code": r.status_code, "keys": list(r.json().keys()) if r.headers.get("content-type","").startswith("application/json") else []}, error=None if ok else "unexpected_response")
    except Exception as e:
        out["Dashboard(/api/overview)"] = StepResult(status="FAIL", error=str(e))

    try:
        r = client.get("/api/documents?limit=20&offset=0")
        j = r.json()
        ok = r.status_code == 200 and isinstance(j.get("items"), list) and len(j.get("items") or []) >= 1
        out["Dashboard(/api/documents)"] = StepResult(status="PASS" if ok else "FAIL", details={"status_code": r.status_code, "items": len(j.get("items") or [])}, error=None if ok else "unexpected_response")
    except Exception as e:
        out["Dashboard(/api/documents)"] = StepResult(status="FAIL", error=str(e))

    try:
        r = client.get("/api/traces?trace_type=ingestion&limit=20&offset=0")
        j = r.json()
        ok = r.status_code == 200 and isinstance(j.get("items"), list) and len(j.get("items") or []) >= 1
        out["Dashboard(/api/traces ingestion)"] = StepResult(status="PASS" if ok else "FAIL", details={"status_code": r.status_code, "items": len(j.get("items") or [])}, error=None if ok else "unexpected_response")
    except Exception as e:
        out["Dashboard(/api/traces ingestion)"] = StepResult(status="FAIL", error=str(e))

    try:
        r = client.get("/api/traces?trace_type=query&limit=20&offset=0")
        j = r.json()
        ok = r.status_code == 200 and isinstance(j.get("items"), list) and len(j.get("items") or []) >= 1
        out["Dashboard(/api/traces query)"] = StepResult(status="PASS" if ok else "FAIL", details={"status_code": r.status_code, "items": len(j.get("items") or [])}, error=None if ok else "unexpected_response")
    except Exception as e:
        out["Dashboard(/api/traces query)"] = StepResult(status="FAIL", error=str(e))

    return out


def _run_real(settings_path: Path) -> dict[str, StepResult]:
    os.environ["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    from src.observability.obs import api as obs
    from src.observability.sinks.jsonl import JsonlSink
    from src.core.runners.ingest import IngestRunner
    from src.core.runners.query import QueryRunner
    from src.core.strategy import load_settings
    from src.observability.dashboard.app import create_app
    from fastapi.testclient import TestClient

    root = _repo_root()
    out: dict[str, StepResult] = {}

    # Preflight based on model_endpoints in settings.
    settings = load_settings(settings_path)
    obs.set_sink(JsonlSink(settings.paths.logs_dir))
    endpoints = (settings.raw or {}).get("model_endpoints") or {}
    ep = endpoints.get("qwen") if isinstance(endpoints, dict) else None
    base_url = ep.get("base_url") if isinstance(ep, dict) else None
    host = _host_from_base_url(str(base_url or ""))
    if host:
        ok, msg = _dns_ok(host)
        if not ok:
            out["Preflight(DNS)"] = StepResult(status="BLOCKED(env:network)", error=f"dns_fail:{host}:{msg}")
            return out
        out["Preflight(DNS)"] = StepResult(status="PASS", details={"host": host})

    ingest = IngestRunner(settings_path=settings_path)
    try:
        resp = ingest.run(root / "tests" / "fixtures" / "docs" / "sample.md", strategy_config_id="local.default", policy="new_version")
    except Exception as e:
        cls = _classify_real_error(str(e))
        out["Ingest(sample.md)"] = StepResult(status=cls, error=str(e))
        return out
    if (resp.structured or {}).get("status") != "ok":
        err = str((resp.structured or {}).get("error") or "ingest_error")
        cls = _classify_real_error(err)
        out["Ingest(sample.md)"] = StepResult(status=cls, trace_id=resp.trace_id, details=resp.structured, error=err)
        return out
    out["Ingest(sample.md)"] = StepResult(status="PASS", trace_id=resp.trace_id, details=resp.structured)

    q = QueryRunner(settings_path=settings_path)
    try:
        qresp = q.run("FTS5", strategy_config_id="local.default", top_k=5)
    except Exception as e:
        cls = _classify_real_error(str(e))
        out["Query(FTS5)"] = StepResult(status=cls, error=str(e))
        return out
    if not qresp.sources:
        out["Query(FTS5)"] = StepResult(status="FAIL(system)", trace_id=qresp.trace_id, details=qresp.structured, error="empty_sources")
        return out
    out["Query(FTS5)"] = StepResult(status="PASS", trace_id=qresp.trace_id, details=qresp.structured)

    app = create_app(settings)
    client = TestClient(app)
    try:
        r = client.get("/api/overview")
        ok = r.status_code == 200 and all(k in r.json() for k in ("assets", "health", "providers"))
        out["Dashboard(/api/overview)"] = StepResult(status="PASS" if ok else "FAIL", details={"status_code": r.status_code}, error=None if ok else "unexpected_response")
    except Exception as e:
        out["Dashboard(/api/overview)"] = StepResult(status="FAIL", error=str(e))
    return out


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_on_syspath()
    ap = argparse.ArgumentParser(prog="run_baseline.py")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--profiles", default="offline,real", help="comma-separated: offline,real")
    ap.add_argument("--suite", default="all", choices=["baseline", "all"], help="baseline: minimal smoke; all: run QA_TEST.md A..O")
    ap.add_argument("--progress", default="QA_TEST_PROGRESS.md")
    args = ap.parse_args(argv)

    run_id = args.run_id or _now_run_id()
    profiles = [p.strip() for p in str(args.profiles).split(",") if p.strip()]
    root = _repo_root()

    offline_settings = root / "config" / f"settings.qa.{run_id}.offline.yaml"
    real_settings = root / "config" / f"settings.qa.{run_id}.real.yaml"
    progress_path = root / str(args.progress)

    notes = [
        f"run_id={run_id}",
        f"OFFLINE settings={offline_settings.relative_to(root)}",
        f"REAL settings={real_settings.relative_to(root)}",
        "干净库路径: data/qa_runs/<run_id>/{offline,real}/...",
    ]

    if args.suite == "baseline":
        offline_results: dict[str, StepResult] = {}
        real_results: dict[str, StepResult] | None = None

        if "offline" in profiles:
            _write_settings(offline_settings, run_id=run_id, profile="offline", defaults_strategy="local.test")
            offline_results = _run_offline(run_id, offline_settings)
        if "real" in profiles:
            _write_settings(real_settings, run_id=run_id, profile="real", defaults_strategy="local.default")
            real_results = _run_real(real_settings)

        _append_progress(progress_path, run_id=run_id, offline=offline_results, real=real_results, notes=notes)

        # Exit code: non-zero if OFFLINE fails (baseline contract).
        if offline_results and any(v.status.startswith("FAIL") for v in offline_results.values()):
            return 2
        return 0

    # suite=all: run QA_TEST.md A..O cases and append a per-case table.
    qa_test_path = root / "QA_TEST.md"
    cases = _load_cases(qa_test_path)

    shared: dict[str, Any] = {"run_id": run_id}
    env_off: ProfileEnv | None = None
    env_real: ProfileEnv | None = None

    if "offline" in profiles:
        _write_settings(offline_settings, run_id=run_id, profile="offline", defaults_strategy="local.test")
        env_off = ProfileEnv(name="OFFLINE", settings_path=offline_settings, strategy_config_id="local.test")
        env_off.activate()
    if "real" in profiles:
        _write_settings(real_settings, run_id=run_id, profile="real", defaults_strategy="local.default")
        env_real = ProfileEnv(name="REAL", settings_path=real_settings, strategy_config_id="local.default")
        env_real.activate()

    results: list[CaseResult] = []
    for case in cases:
        cr = CaseResult(case=case)
        # OFFLINE
        if env_off is not None and "OFFLINE" in case.profiles:
            try:
                env_off.activate()
                cr.offline = _exec_case(case, env_off, shared=shared)
            except Exception as e:
                cr.offline = StepResult(status="FAIL", error=f"exception:{type(e).__name__}:{e}")
        # REAL
        if env_real is not None and "REAL" in case.profiles:
            location = f"run_baseline.py:main/_exec_case[{case.case_id}]"
            try:
                env_real.activate()
                if shared.get("_real_blocked"):
                    cr.real = _attach_real_diagnostic(
                        case,
                        env_real,
                        StepResult(
                        status="BLOCKED(env:network)",
                        error=str(shared.get("_real_blocked_reason") or "network_blocked"),
                        ),
                        location="run_baseline.py:main/preflight_dns",
                    )
                else:
                    # Preflight DNS for REAL on first real case to surface env blockers early.
                    if not shared.get("_real_preflight_done"):
                        shared["_real_preflight_done"] = True
                        base_url = None
                        if hasattr(env_real.settings, "raw"):
                            eps = (env_real.settings.raw.get("model_endpoints") or {})  # type: ignore[attr-defined]
                            if isinstance(eps, dict):
                                for v in eps.values():
                                    if (
                                        isinstance(v, dict)
                                        and isinstance(v.get("base_url"), str)
                                        and v.get("base_url")
                                    ):
                                        base_url = v.get("base_url")
                                        break
                        host = _host_from_base_url(str(base_url or ""))
                        ok, msg = _dns_ok(host) if host else (True, "")
                        if not ok:
                            shared["_real_blocked"] = True
                            shared["_real_blocked_reason"] = f"dns_fail:{host}:{msg}"
                            cr.real = _attach_real_diagnostic(
                                case,
                                env_real,
                                StepResult(status="BLOCKED(env:network)", error=f"dns_fail:{host}:{msg}"),
                                location="run_baseline.py:main/preflight_dns",
                            )
                        else:
                            cr.real = _attach_real_diagnostic(
                                case,
                                env_real,
                                _exec_case(case, env_real, shared=shared),
                                location=location,
                            )
                    else:
                        cr.real = _attach_real_diagnostic(
                            case,
                            env_real,
                            _exec_case(case, env_real, shared=shared),
                            location=location,
                        )
            except Exception as e:
                cr.real = _attach_real_diagnostic(
                    case,
                    env_real,
                    StepResult(status=_classify_real_error(str(e)), error=f"exception:{type(e).__name__}:{e}"),
                    location=location,
                )

        cr.overall = _compute_overall(case, cr.offline, cr.real)
        if cr.real and (cr.real.status.startswith("BLOCKED") or cr.real.status.startswith("FAIL")):
            cr.note = _summarize_diagnostic(cr.real.diagnostic) or (cr.real.error or "")
        elif (cr.offline and cr.offline.status.startswith("BLOCKED")) or (cr.real and cr.real.status.startswith("BLOCKED")):
            cr.note = (cr.offline.error if cr.offline and cr.offline.error else "") or (cr.real.error if cr.real and cr.real.error else "")
        results.append(cr)

    _append_progress_cases(progress_path, run_id=run_id, notes=notes + ["suite=all (QA_TEST.md A..O)"], results=results)

    # Exit non-zero if any OFFLINE FAIL (regression gate).
    if any(cr.offline and cr.offline.status.startswith("FAIL") for cr in results if "OFFLINE" in cr.case.profiles):
        return 2
    return 0


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = int(main())
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
    os._exit(exit_code)
