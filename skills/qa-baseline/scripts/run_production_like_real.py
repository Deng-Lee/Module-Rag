from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _now_run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_repo_on_syspath() -> None:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def _yaml_dump_simple(d: dict[str, Any]) -> str:
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


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        cur = out.get(k)
        if isinstance(cur, dict) and isinstance(v, dict):
            out[k] = _merge_dicts(cur, v)
        else:
            out[k] = v
    return out


def _write_settings(path: Path, *, run_id: str, strategy_config_id: str) -> None:
    root = _repo_root()
    profile = "production_like_real"
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
        "defaults": {"strategy_config_id": strategy_config_id},
        "eval": {"datasets_dir": "tests/datasets"},
        "providers": {
            "embedder": {"params": {"timeout_s": 20}},
            "llm": {"params": {"timeout_s": 30}},
            "reranker": {"params": {"timeout_s": 30}},
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
                    "model": "qwen-turbo",
                    "embedding_model": "text-embedding-v3",
                },
            },
            "enricher": {"provider_id": "noop"},
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Production-like REAL strategy settings (generated)\n"
        "# DO NOT COMMIT\n"
        f"# run_id: {run_id}\n" + _yaml_dump_simple(obj),
        encoding="utf-8",
    )


def _activate(settings_path: Path) -> Any:
    _ensure_repo_on_syspath()
    os.environ["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    os.environ["MODULE_RAG_SECRETS_PATH"] = str(settings_path.parent / "__NO_OVERRIDE__.yaml")
    os.environ.pop("MODULE_RAG_MODEL_ENDPOINTS_PATH", None)

    from src.core.strategy import load_settings
    from src.observability.obs import api as obs
    from src.observability.sinks.jsonl import JsonlSink

    settings = load_settings(settings_path)
    obs.set_sink(JsonlSink(settings.paths.logs_dir))
    return settings


def _host_from_base_url(base_url: str) -> str:
    s = (base_url or "").strip()
    s = s.replace("https://", "").replace("http://", "")
    s = s.split("/")[0]
    return s.split(":")[0]


def _dns_ok(host: str) -> tuple[bool, str]:
    try:
        socket.getaddrinfo(host, 443)
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _load_jsonish(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _materialize_retrieval_docs(run_dir: Path) -> list[Path]:
    payload = _load_jsonish(_repo_root() / "tests" / "datasets" / "retrieval_small.yaml")
    out_dir = run_dir / "fixtures"
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for doc in payload.get("docs") or []:
        if not isinstance(doc, dict):
            continue
        name = str(doc.get("name") or "").strip()
        md = str(doc.get("md") or "")
        if not name or not md:
            continue
        p = out_dir / f"{name}.md"
        p.write_text(md, encoding="utf-8")
        out.append(p)
    return out


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


@dataclass
class ProdLikeResult:
    status: str
    query_trace_id: str | None = None
    eval_run_id: str | None = None
    metrics: dict[str, float] | None = None
    details: dict[str, Any] | None = None
    error: str | None = None


def _run_chain(settings_path: Path, *, strategy_config_id: str, top_k: int) -> ProdLikeResult:
    settings = _activate(settings_path)

    model_endpoints = (settings.raw.get("model_endpoints") or {}) if isinstance(settings.raw, dict) else {}
    qwen_ep = model_endpoints.get("qwen") if isinstance(model_endpoints, dict) else None
    base_url = str((qwen_ep or {}).get("base_url") or "")
    host = _host_from_base_url(base_url)
    if host:
        ok, msg = _dns_ok(host)
        if not ok:
            return ProdLikeResult(
                status="BLOCKED(env:network)",
                error=f"dns_fail:{host}:{msg}",
                details={"stage": "preflight_dns", "host": host},
            )

    from src.core.runners.eval import EvalRunner
    from src.core.runners.ingest import IngestRunner
    from src.core.runners.query import QueryRunner

    run_dir = settings.paths.data_dir
    docs = _materialize_retrieval_docs(run_dir)
    if not docs:
        return ProdLikeResult(status="FAIL", error="no_materialized_docs")

    ingester = IngestRunner(settings_path=settings_path)
    ingested: list[dict[str, Any]] = []
    for doc in docs:
        resp = ingester.run(doc, strategy_config_id=strategy_config_id, policy="new_version")
        structured = dict(resp.structured or {})
        if structured.get("status") not in {"ok", "skipped"}:
            return ProdLikeResult(
                status="FAIL",
                error=str(structured.get("error") or "ingest_failed"),
                details={"stage": "ingest", "file": str(doc), "structured": structured},
            )
        ingested.append({"file": str(doc), "trace_id": resp.trace_id, "structured": structured})

    query_runner = QueryRunner(settings_path=settings_path, settings=settings)
    query = "Explain SQLite FTS5 inverted index and BM25."
    qresp = query_runner.run(query, strategy_config_id=strategy_config_id, top_k=top_k)
    if not qresp.sources:
        return ProdLikeResult(status="FAIL", error="query_empty_sources", details={"stage": "query"})
    if qresp.trace is None:
        return ProdLikeResult(status="FAIL", error="query_missing_trace")

    providers = qresp.trace.providers or {}
    if ((providers.get("embedder") or {}).get("provider_id")) != "openai_compatible":
        return ProdLikeResult(status="FAIL", error="embedder_not_real", details={"providers": providers})
    if ((providers.get("llm") or {}).get("provider_id")) != "openai_compatible":
        return ProdLikeResult(status="FAIL", error="llm_not_real", details={"providers": providers})
    if ((providers.get("reranker") or {}).get("provider_id")) != "openai_compatible_llm":
        return ProdLikeResult(status="FAIL", error="reranker_not_real", details={"providers": providers})
    if _trace_has_event(qresp.trace, "stage.generate", "warn.generate_fallback"):
        return ProdLikeResult(status="FAIL", query_trace_id=qresp.trace_id, error="llm_generate_fallback")
    if not _trace_has_event(qresp.trace, "stage.generate", "generate.used"):
        return ProdLikeResult(status="FAIL", query_trace_id=qresp.trace_id, error="missing_generate_used")
    if _trace_has_event(qresp.trace, "stage.rerank", "warn.rerank_fallback"):
        return ProdLikeResult(status="FAIL", query_trace_id=qresp.trace_id, error="rerank_fallback")
    rerank_used = _last_trace_event(qresp.trace, "stage.rerank", "rerank.used")
    if rerank_used is None or rerank_used.attrs.get("rerank_applied") is not True:
        return ProdLikeResult(status="FAIL", query_trace_id=qresp.trace_id, error="rerank_not_applied")

    evaluator = EvalRunner(settings_path=settings_path, settings=settings)
    eval_result = evaluator.run("production_like_eval_smoke", strategy_config_id=strategy_config_id, top_k=top_k)
    ragas_metrics = {k: float(v) for k, v in (eval_result.metrics or {}).items() if k.startswith("ragas.")}
    if not ragas_metrics:
        case_artifacts = eval_result.cases[0].artifacts if eval_result.cases else {}
        return ProdLikeResult(
            status="FAIL",
            query_trace_id=qresp.trace_id,
            eval_run_id=eval_result.run_id,
            error="ragas_metrics_missing",
            details={"stage": "eval", "artifacts": case_artifacts, "metrics": eval_result.metrics},
        )
    if any(math.isnan(v) for v in ragas_metrics.values()):
        return ProdLikeResult(
            status="FAIL",
            query_trace_id=qresp.trace_id,
            eval_run_id=eval_result.run_id,
            error="ragas_metrics_nan",
            details={"stage": "eval", "metrics": ragas_metrics},
        )

    return ProdLikeResult(
        status="PASS",
        query_trace_id=qresp.trace_id,
        eval_run_id=eval_result.run_id,
        metrics=ragas_metrics,
        details={
            "providers": providers,
            "ingested": ingested,
            "source_count": len(qresp.sources),
            "rerank_profile_id": ((providers.get("reranker") or {}).get("rerank_profile_id")),
        },
    )


def _append_progress(progress_path: Path, *, run_id: str, settings_path: Path, result: ProdLikeResult) -> None:
    root = _repo_root()
    lines: list[str] = []
    lines.append("")
    lines.append(f"## Run: {run_id}（Production-like REAL strategy 专项回归）")
    lines.append("")
    lines.append("### 本次做了什么")
    lines.append("")
    lines.append(f"- run_id={run_id}")
    lines.append(f"- settings={settings_path.relative_to(root)}")
    lines.append("- strategy=local.production_like")
    lines.append("- chain=ingest -> query -> rerank -> eval")
    lines.append("- providers=embedder(openai_compatible/qwen) + llm(openai_compatible/qwen) + reranker(openai_compatible_llm/qwen) + evaluator(ragas/qwen)")
    lines.append("")
    lines.append("### 结果是什么")
    lines.append("")
    if result.status == "PASS":
        lines.append(f"- Status=PASS, query_trace_id={result.query_trace_id}, eval_run_id={result.eval_run_id}")
        lines.append(f"- Metrics={json.dumps(result.metrics or {}, ensure_ascii=False)}")
        lines.append(f"- Details={json.dumps(result.details or {}, ensure_ascii=False)}")
    else:
        lines.append(f"- Status={result.status}, error={result.error}")
        if result.query_trace_id:
            lines.append(f"- query_trace_id={result.query_trace_id}")
        if result.eval_run_id:
            lines.append(f"- eval_run_id={result.eval_run_id}")
        if result.details:
            lines.append(f"- Details={json.dumps(result.details, ensure_ascii=False)}")
    lines.append("")
    lines.append("### 下一步是什么")
    lines.append("")
    if result.status == "PASS":
        lines.append("- 可将这条专项回归固定到发版前检查，和 A..O baseline 分开维护。")
    else:
        lines.append("- 按 Details 中的 stage/artifacts 定位 provider、模型和失败环节，再重跑本脚本。")
    lines.append("")
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    with progress_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_on_syspath()
    ap = argparse.ArgumentParser(prog="run_production_like_real.py")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--progress", default="QA_TEST_PROGRESS.md")
    ap.add_argument("--top-k", default=5, type=int)
    args = ap.parse_args(argv)

    run_id = args.run_id or _now_run_id()
    root = _repo_root()
    settings_path = root / "config" / f"settings.prodlike.{run_id}.real.yaml"
    progress_path = root / str(args.progress)

    _write_settings(settings_path, run_id=run_id, strategy_config_id="local.production_like")
    result = _run_chain(settings_path, strategy_config_id="local.production_like", top_k=int(args.top_k))
    _append_progress(progress_path, run_id=run_id, settings_path=settings_path, result=result)
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
