# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_dashboard_consistency import run_dashboard_checks
from compare_profiles import run_compare
from qa_plus_common import (
    CaseResult,
    FailureInfo,
    REAL_COMPARE_DEFAULTS,
    activate_runtime,
    build_failure,
    ensure_repo_on_syspath,
    find_error_event,
    fixture_path,
    json_dump,
    json_loads_safe,
    merged_provider_specs,
    now_run_id,
    preflight_real,
    safe_metric_dict,
    settings_path_for,
    strategy_path_for,
    summary_counts,
    traces_have_event,
    write_real_settings,
    write_strategy_yaml,
)


def _case(
    case_id: str, title: str, entry: str, strategy_config_id: str, status: str = "PASS"
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        title=title,
        entry=entry,
        strategy_config_id=strategy_config_id,
        status=status,
    )


def _failure_from_exc(
    *,
    stage: str,
    location: str,
    provider_model: str,
    exc: Exception,
    fallback: str = "not_triggered",
) -> FailureInfo:
    return build_failure(
        stage=stage,
        location=location,
        provider_model=provider_model,
        raw_error=f"{type(exc).__name__}: {exc}",
        fallback=fallback,
    )


def _write_png(path: Path) -> None:
    png_bytes = bytes.fromhex(
        "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
        "0000000A49444154789C6360000002000154010D0A0000000049454E44AE426082"
    )
    path.write_bytes(png_bytes)


def _find_trace_event(
    trace: Any,
    *,
    span_name: str | None = None,
    kind_contains: str | None = None,
) -> dict[str, Any] | None:
    if trace is None:
        return None
    for span in getattr(trace, "spans", None) or []:
        if span_name and getattr(span, "name", None) != span_name:
            continue
        for event in getattr(span, "events", None) or []:
            kind = str(getattr(event, "kind", "") or "")
            if kind_contains and kind_contains not in kind:
                continue
            return {
                "span": getattr(span, "name", None),
                "kind": kind,
                "attrs": getattr(event, "attrs", None) or {},
            }
    return None


def _dashboard_client(settings_path: Path) -> Any:
    settings = activate_runtime(settings_path)
    from fastapi.testclient import TestClient

    from src.observability.dashboard.app import create_app

    return TestClient(create_app(settings))


def _run_query_cli(
    *,
    query: str,
    strategy_config_id: str,
    top_k: int,
    settings_path: Path,
    verbose: bool = False,
) -> dict[str, Any]:
    cmd = [
        "bash",
        "scripts/dev_query.sh",
        query,
        strategy_config_id,
        str(top_k),
    ]
    if verbose:
        cmd.append("--verbose")
    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    proc = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    stdout = proc.stdout
    verbose_payload: dict[str, Any] = {}
    begin = "=== VERBOSE DETAILS BEGIN ==="
    end = "=== VERBOSE DETAILS END ==="
    if begin in stdout and end in stdout:
        raw = stdout.split(begin, 1)[1].split(end, 1)[0].strip()
        verbose_payload = json_loads_safe(raw)
    trace_id = ""
    for line in reversed(stdout.splitlines()):
        if line.startswith("trace_id:"):
            trace_id = line.split(":", 1)[1].strip()
            break
    return {
        "stdout": stdout,
        "stderr": proc.stderr,
        "trace_id": trace_id,
        "verbose": verbose_payload,
    }


def _run_ingest_cli(
    *,
    file_path: Path,
    strategy_config_id: str,
    policy: str,
    settings_path: Path,
    verbose: bool = False,
) -> dict[str, Any]:
    cmd = [
        "bash",
        "scripts/dev_ingest.sh",
        str(file_path),
        strategy_config_id,
        policy,
    ]
    if verbose:
        cmd.append("--verbose")
    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    proc = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    stdout = proc.stdout
    verbose_payload: dict[str, Any] = {}
    begin = "=== VERBOSE DETAILS BEGIN ==="
    end = "=== VERBOSE DETAILS END ==="
    if begin in stdout and end in stdout:
        raw = stdout.split(begin, 1)[1].split(end, 1)[0].strip()
        verbose_payload = json_loads_safe(raw)
    trace_id = ""
    for line in reversed(stdout.splitlines()):
        if line.startswith("trace_id:"):
            trace_id = line.split(":", 1)[1].strip()
            break
    return {
        "stdout": stdout,
        "stderr": proc.stderr,
        "trace_id": trace_id,
        "verbose": verbose_payload,
    }


def _run_eval_cli(
    *,
    dataset_id: str,
    strategy_config_id: str,
    top_k: int,
    settings_path: Path,
    verbose: bool = False,
) -> dict[str, Any]:
    cmd = [
        "bash",
        "scripts/dev_eval.sh",
        dataset_id,
        strategy_config_id,
        str(top_k),
    ]
    if verbose:
        cmd.append("--verbose")
    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    proc = subprocess.run(
        cmd,
        cwd=Path(__file__).resolve().parents[3],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    stdout = proc.stdout
    verbose_payload: dict[str, Any] = {}
    begin = "=== VERBOSE DETAILS BEGIN ==="
    end = "=== VERBOSE DETAILS END ==="
    if begin in stdout and end in stdout:
        raw = stdout.split(begin, 1)[1].split(end, 1)[0].strip()
        try:
            value = json.loads(raw)
            if isinstance(value, dict):
                verbose_payload = value
        except Exception:
            verbose_payload = {}
    return {
        "stdout": stdout,
        "stderr": proc.stderr,
        "verbose": verbose_payload,
    }


def _runtime_bundle(settings_path: Path) -> dict[str, Any]:
    ensure_repo_on_syspath()
    from src.core.runners.admin import AdminRunner
    from src.core.runners.eval import EvalRunner
    from src.core.runners.ingest import IngestRunner
    from src.core.runners.query import QueryRunner
    from src.ingestion.stages.storage.sqlite import SqliteStore

    settings = activate_runtime(settings_path)
    return {
        "settings": settings,
        "ingester": IngestRunner(settings_path=settings_path),
        "query_runner": QueryRunner(settings_path=settings_path, settings=settings),
        "eval_runner": EvalRunner(settings_path=settings_path, settings=settings),
        "admin_runner": AdminRunner(settings_path=settings_path),
        "sqlite": SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite"),
    }


def _make_settings(
    *,
    run_id: str,
    suffix: str,
    strategy_config_id: str,
    providers_override: dict[str, Any] | None = None,
) -> Path:
    settings_path = settings_path_for(run_id, suffix=suffix)
    write_real_settings(
        settings_path,
        run_id=run_id,
        suffix=suffix,
        strategy_config_id=strategy_config_id,
        providers_override=providers_override,
    )
    return settings_path


def _run_mcp_stdio(settings_path: Path) -> dict[str, Any]:
    ensure_repo_on_syspath()
    import os

    env = dict(os.environ)
    env["MODULE_RAG_SETTINGS_PATH"] = str(settings_path)
    repo_root = Path(__file__).resolve().parents[3]
    simple_pdf = fixture_path("simple.pdf")
    with_images_pdf = fixture_path("with_images.pdf")
    cmd = [sys.executable, "-m", "src.mcp_server.entry"]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(repo_root),
        env=env,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    def call(req: dict[str, Any]) -> dict[str, Any]:
        proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline().strip()
        return json.loads(line)

    payload: dict[str, Any] = {
        "tools_list": {"status": "FAIL"},
        "ingest": {"status": "FAIL"},
        "query": {"status": "FAIL"},
        "get_document": {"status": "FAIL"},
        "summarize_document": {"status": "FAIL"},
        "multimodal_query": {"status": "FAIL"},
        "session_stability": {"status": "FAIL"},
        "citation_transparency": {"status": "FAIL"},
        "list_documents": {"status": "FAIL"},
        "delete": {"status": "FAIL"},
        "query_assets": {"status": "FAIL"},
        "invalid_params": {"status": "FAIL"},
    }
    try:
        tools = call({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        names = {tool.get("name") for tool in tools["result"]["tools"]}
        expected = {
            "library_ingest",
            "library_query",
            "library_query_assets",
            "library_list_documents",
            "library_get_document",
            "library_summarize_document",
            "library_delete_document",
            "library_ping",
        }
        payload["tools_list"] = {
            "status": "PASS" if expected.issubset(names) else "FAIL",
            "tool_names": sorted(names),
        }

        simple_ingest = call(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "library_ingest",
                    "arguments": {"file_path": str(simple_pdf)},
                },
            }
        )
        ingest_structured = (
            ((simple_ingest.get("result") or {}).get("structuredContent") or {}).get("structured")
        ) or {}
        payload["ingest"] = {
            "status": "PASS"
            if ingest_structured.get("status") in {"ok", "skipped"}
            else "FAIL",
            "structured": ingest_structured,
        }
        doc_id = str(ingest_structured.get("doc_id") or "")
        version_id = str(ingest_structured.get("version_id") or "")

        images_ingest = call(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "library_ingest",
                    "arguments": {"file_path": str(with_images_pdf)},
                },
            }
        )
        images_structured = (
            ((images_ingest.get("result") or {}).get("structuredContent") or {}).get("structured")
        ) or {}
        images_doc_id = str(images_structured.get("doc_id") or "")
        if doc_id and version_id:
            got = call(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "library_get_document",
                        "arguments": {
                            "doc_id": doc_id,
                            "version_id": version_id,
                            "max_chars": 4000,
                        },
                    },
                }
            )
            gsc = (got.get("result") or {}).get("structuredContent") or {}
            gstructured = gsc.get("structured") or {}
            text = (got.get("result") or {}).get("content") or []
            text_joined = "\n".join(
                item.get("text", "")
                for item in text
                if isinstance(item, dict) and item.get("type") == "text"
            )
            payload["get_document"] = {
                "status": (
                    "PASS"
                    if gstructured.get("doc_id") == doc_id
                    and gstructured.get("version_id") == version_id
                    and "hello world" in text_joined.lower()
                    else "FAIL"
                ),
                "doc_id": gstructured.get("doc_id"),
                "version_id": gstructured.get("version_id"),
                "warnings": gstructured.get("warnings") or [],
                "text_preview": text_joined[:120],
            }
        else:
            payload["get_document"] = {
                "status": "FAIL",
                "doc_id": doc_id,
                "version_id": version_id,
                "warnings": [],
                "text_preview": "",
            }

        if doc_id and version_id:
            summarized = call(
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "library_summarize_document",
                        "arguments": {
                            "doc_id": doc_id,
                            "version_id": version_id,
                            "max_chars": 240,
                            "max_segments": 3,
                        },
                    },
                }
            )
            ssc = (summarized.get("result") or {}).get("structuredContent") or {}
            sstructured = ssc.get("structured") or {}
            scontent = (summarized.get("result") or {}).get("content") or []
            summary_text = "\n".join(
                item.get("text", "")
                for item in scontent
                if isinstance(item, dict) and item.get("type") == "text"
            )
            payload["summarize_document"] = {
                "status": (
                    "PASS"
                    if sstructured.get("doc_id") == doc_id
                    and sstructured.get("version_id") == version_id
                    and bool(summary_text.strip())
                    else "FAIL"
                ),
                "doc_id": sstructured.get("doc_id"),
                "version_id": sstructured.get("version_id"),
                "warnings": sstructured.get("warnings") or [],
                "summary_char_count": sstructured.get("summary_char_count"),
                "summary_preview": summary_text[:120],
            }
        else:
            payload["summarize_document"] = {
                "status": "FAIL",
                "doc_id": doc_id,
                "version_id": version_id,
                "warnings": [],
                "summary_char_count": 0,
                "summary_preview": "",
            }

        query = call(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "library_query",
                    "arguments": {"query": "Sample Document PDF loader", "top_k": 3},
                },
            }
        )
        qsc = (query.get("result") or {}).get("structuredContent") or {}
        sources = qsc.get("sources") or []
        payload["query"] = {
            "status": "PASS" if isinstance(sources, list) and sources else "FAIL",
            "source_count": len(sources),
            "top_doc_id": sources[0].get("doc_id") if sources else None,
            "top_chunk_id": sources[0].get("chunk_id") if sources else None,
            "top_section_path": sources[0].get("section_path") if sources else None,
        }
        payload["citation_transparency"] = {
            "status": (
                "PASS"
                if sources
                and any(source.get("doc_id") == doc_id for source in sources)
                and all(
                    source.get("doc_id")
                    and source.get("chunk_id")
                    and isinstance(source.get("score"), (int, float))
                    and source.get("section_path")
                    for source in sources
                )
                else "FAIL"
            ),
            "source_count": len(sources),
            "expected_doc_id": doc_id,
            "top_source": sources[0] if sources else {},
        }

        multimodal = call(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "library_query",
                    "arguments": {"query": "Document with Images embedded image below", "top_k": 3},
                },
            }
        )
        msc = (multimodal.get("result") or {}).get("structuredContent") or {}
        multi_sources = msc.get("sources") or []
        asset_ids: list[str] = []
        for source in multi_sources:
            for asset_id in source.get("asset_ids") or []:
                if asset_id:
                    asset_ids.append(asset_id)

        if asset_ids:
            assets_resp = call(
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "library_query_assets",
                        "arguments": {"asset_ids": asset_ids[:1], "max_bytes": 200000},
                    },
                }
            )
            assets = (
                ((assets_resp.get("result") or {}).get("structuredContent") or {}).get(
                    "structured"
                )
                or {}
            ).get("assets") or []
            payload["query_assets"] = {
                "status": "PASS" if assets else "FAIL",
                "asset_count": len(assets),
            }
            payload["multimodal_query"] = {
                "status": (
                    "PASS"
                    if multi_sources
                    and images_doc_id
                    and any(source.get("doc_id") == images_doc_id for source in multi_sources)
                    and bool(assets)
                    else "FAIL"
                ),
                "source_count": len(multi_sources),
                "asset_ids": asset_ids[:3],
                "asset_count": len(assets),
                "top_source": multi_sources[0] if multi_sources else {},
            }
        else:
            payload["query_assets"] = {
                "status": "FAIL",
                "asset_count": 0,
            }
            payload["multimodal_query"] = {
                "status": "FAIL",
                "source_count": len(multi_sources),
                "asset_ids": [],
                "asset_count": 0,
                "top_source": multi_sources[0] if multi_sources else {},
            }

        listed = call(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "library_list_documents",
                    "arguments": {"include_deleted": True},
                },
            }
        )
        items = (
            ((listed.get("result") or {}).get("structuredContent") or {}).get("structured") or {}
        ).get("items") or []
        payload["list_documents"] = {
            "status": (
                "PASS"
                if doc_id
                and images_doc_id
                and any(item.get("doc_id") == doc_id for item in items)
                and any(item.get("doc_id") == images_doc_id for item in items)
                else "FAIL"
            ),
            "doc_count": len(items),
            "doc_id": doc_id,
            "images_doc_id": images_doc_id,
        }

        stability_queries = [
            "Sample Document PDF loader",
            "A Simple Test PDF",
            "Section 1 Introduction",
            "Document with Images",
            "embedded image below",
        ]
        stability_runs: list[dict[str, Any]] = []
        for idx, stability_query in enumerate(stability_queries, start=10):
            start = time.perf_counter()
            stability_resp = call(
                {
                    "jsonrpc": "2.0",
                    "id": idx,
                    "method": "tools/call",
                    "params": {
                        "name": "library_query",
                        "arguments": {"query": stability_query, "top_k": 3},
                    },
                }
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000.0, 3)
            stability_sc = (stability_resp.get("result") or {}).get("structuredContent") or {}
            stability_sources = stability_sc.get("sources") or []
            stability_runs.append(
                {
                    "query": stability_query,
                    "elapsed_ms": elapsed_ms,
                    "source_count": len(stability_sources),
                }
            )
        latencies = [float(run["elapsed_ms"]) for run in stability_runs]
        min_latency_ms = min(latencies) if latencies else 0.0
        max_latency_ms = max(latencies) if latencies else 0.0
        payload["session_stability"] = {
            "status": (
                "PASS"
                if all(run["source_count"] > 0 for run in stability_runs)
                and max_latency_ms
                <= max(
                    5000.0,
                    min_latency_ms * 5.0 if min_latency_ms else 5000.0,
                )
                else "FAIL"
            ),
            "runs": stability_runs,
            "min_latency_ms": min_latency_ms,
            "max_latency_ms": max_latency_ms,
        }

        deleted = call(
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {"name": "library_delete_document", "arguments": {"doc_id": doc_id}},
            }
        )
        delete_structured = (
            ((deleted.get("result") or {}).get("structuredContent") or {}).get("structured")
        ) or {}
        query_after = call(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "tools/call",
                "params": {
                    "name": "library_query",
                    "arguments": {"query": "Sample Document PDF loader", "top_k": 3},
                },
            }
        )
        sources_after = ((query_after.get("result") or {}).get("structuredContent") or {}).get(
            "sources"
        ) or []
        payload["delete"] = {
            "status": "PASS"
            if delete_structured.get("status") in {"ok", "noop"}
            and not any(source.get("doc_id") == doc_id for source in sources_after)
            else "FAIL",
            "delete_status": delete_structured.get("status"),
            "query_after_count": len(sources_after),
        }

        invalid = call(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {"name": "library_query_assets", "arguments": {}},
            }
        )
        error = invalid.get("error") or {}
        payload["invalid_params"] = {
            "status": "PASS" if error.get("code") == -32602 else "FAIL",
            "error": error,
        }
    except Exception as exc:
        payload["fatal_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if proc.stdin:
            try:
                proc.stdin.close()
            except Exception:
                pass
        proc.terminate()
    return payload


def _expected_failure_case(
    case: CaseResult,
    *,
    status: str,
    evidence: dict[str, Any],
    failure: FailureInfo | None = None,
) -> CaseResult:
    case.status = status
    case.evidence = evidence
    if failure is not None:
        case.failure = failure
    return case


def _longest_suffix_prefix_overlap(left: str, right: str, *, max_scan: int = 200) -> int:
    a = str(left or "")
    b = str(right or "")
    if not a or not b:
        return 0
    limit = min(len(a), len(b), max_scan)
    for size in range(limit, 0, -1):
        if a[-size:] == b[:size]:
            return size
    return 0


def _run_single_doc_recall_case(
    *,
    run_id: str,
    suffix: str,
    strategy_config_id: str,
    file_name: str,
    query: str,
    top_k: int,
    required_keywords: list[str] | None = None,
) -> dict[str, Any]:
    settings_path = _make_settings(
        run_id=run_id,
        suffix=suffix,
        strategy_config_id=strategy_config_id,
    )
    bundle = _runtime_bundle(settings_path)
    ingest_resp = bundle["ingester"].run(
        fixture_path(file_name),
        strategy_config_id=strategy_config_id,
        policy="new_version",
    )
    structured = dict(ingest_resp.structured or {})
    doc_id = str(structured.get("doc_id") or "")
    query_resp = bundle["query_runner"].run(
        query, strategy_config_id=strategy_config_id, top_k=top_k
    )
    source_chunk_ids = [src.chunk_id for src in query_resp.sources if src.chunk_id]
    chunk_rows = bundle["sqlite"].fetch_chunks(source_chunk_ids)
    chunk_map = {row.chunk_id: row for row in chunk_rows}
    text_hits = []
    for src in query_resp.sources:
        row = chunk_map.get(src.chunk_id)
        if row is None:
            continue
        text_hits.append(
            {
                "chunk_id": row.chunk_id,
                "doc_id": row.doc_id,
                "section_path": row.section_path,
                "chunk_text_preview": row.chunk_text[:160],
            }
        )
    keywords = required_keywords or []
    matched_keywords = sorted(
        {
            kw
            for kw in keywords
            if any(
                kw.lower() in str(item.get("chunk_text_preview") or "").lower()
                for item in text_hits
            )
        }
    )
    return {
        "settings_path": str(settings_path),
        "doc_id": doc_id,
        "ingest_trace_id": ingest_resp.trace_id,
        "query_trace_id": query_resp.trace_id,
        "source_count": len(query_resp.sources),
        "top_doc_id": query_resp.sources[0].doc_id if query_resp.sources else None,
        "top_chunk_id": query_resp.sources[0].chunk_id if query_resp.sources else None,
        "top_section_path": query_resp.sources[0].section_path if query_resp.sources else None,
        "text_hits": text_hits[:3],
        "matched_keywords": matched_keywords,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=now_run_id())
    p.add_argument("--strategy-config-id", default="local.production_like")
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--write-progress", action="store_true", default=True)
    p.add_argument("--no-write-progress", action="store_true")
    args = p.parse_args()

    write_progress_enabled = args.write_progress and not args.no_write_progress
    run_id = args.run_id
    strategy_config_id = args.strategy_config_id

    cases: list[CaseResult] = []
    evidence: dict[str, Any] = {
        "doc_ids_active": [],
        "doc_ids_by_alias": {},
        "trace_ids": [],
        "ingest_trace_ids": [],
    }

    main_settings_path = _make_settings(
        run_id=run_id,
        suffix="main",
        strategy_config_id=strategy_config_id,
    )

    # A. 环境与预检
    a01 = _case("A-01", "REAL 预检通过", "Provider 预检", strategy_config_id)
    preflight_status, preflight_evidence, preflight_failure = preflight_real(
        main_settings_path, strategy_config_id
    )
    a01.status = "PASS" if preflight_status == "PASS" else "FAIL"
    a01.evidence = preflight_evidence
    if preflight_status != "PASS" and preflight_failure is not None:
        a01.failure = preflight_failure
    cases.append(a01)

    a02 = _case("A-02", "缺失 API Key 的提示", "Provider 预检", strategy_config_id)
    try:
        missing_key_settings = _make_settings(
            run_id=run_id,
            suffix="preflight-missing-key",
            strategy_config_id="local.default",
            providers_override={
                "llm": {
                    "params": {
                        "base_url": "https://example.invalid/v1",
                        "api_key": "",
                    }
                }
            },
        )
        status, ev, failure = preflight_real(missing_key_settings, "local.default")
        a02.status = (
            "PASS"
            if status == "FAIL"
            and (failure is not None and "llm::openai_compatible" in str(failure.provider_model))
            else "FAIL"
        )
        a02.evidence = {"preflight_status": status, "checks": ev.get("checks")}
        if failure is not None:
            a02.failure = failure
    except Exception as exc:
        a02.status = "FAIL"
        a02.failure = _failure_from_exc(
            stage="preflight_missing_key",
            location="run_real_suite.main",
            provider_model="llm::openai_compatible",
            exc=exc,
        )
    cases.append(a02)

    a03 = _case("A-03", "endpoint host 无法解析", "Provider 预检", strategy_config_id)
    try:
        bad_host_settings = _make_settings(
            run_id=run_id,
            suffix="preflight-bad-host",
            strategy_config_id="local.default",
            providers_override={
                "llm": {
                    "params": {
                        "base_url": "http://qa-plus.invalid/v1",
                        "api_key": "qa-plus-key",
                    }
                }
            },
        )
        status, ev, failure = preflight_real(bad_host_settings, "local.default")
        a03.status = (
            "PASS"
            if status.startswith("BLOCKED(env:network)")
            and failure is not None
            and "qa-plus.invalid" in str(failure.raw_error)
            else "FAIL"
        )
        a03.evidence = {"preflight_status": status, "checks": ev.get("checks")}
        if failure is not None:
            a03.failure = failure
    except Exception as exc:
        a03.status = "FAIL"
        a03.failure = _failure_from_exc(
            stage="preflight_dns",
            location="run_real_suite.main",
            provider_model="llm::openai_compatible",
            exc=exc,
        )
    cases.append(a03)

    a05 = _case("A-05", "settings 隔离目录生成正确", "settings writer", strategy_config_id)
    try:
        main_settings = activate_runtime(main_settings_path)
        paths = main_settings.paths
        expected_fragment = f"qa_plus_runs/{run_id}/main"
        checks = {
            "data_dir": str(paths.data_dir),
            "cache_dir": str(paths.cache_dir),
            "logs_dir": str(paths.logs_dir),
            "sqlite_dir": str(paths.sqlite_dir),
        }
        a05.evidence = checks
        if not all(expected_fragment in value for value in checks.values()):
            a05.status = "FAIL"
            a05.failure = build_failure(
                stage="settings_isolation",
                location="run_real_suite.main",
                provider_model="settings::writer",
                raw_error="isolated_paths_missing_run_id",
            )
    except Exception as exc:
        a05.status = "FAIL"
        a05.failure = _failure_from_exc(
            stage="settings_isolation",
            location="run_real_suite.main",
            provider_model="settings::writer",
            exc=exc,
        )
    cases.append(a05)

    a06 = _case("A-06", "model_endpoints 覆盖生效", "settings + provider merge", strategy_config_id)
    try:
        merged = merged_provider_specs(main_settings, strategy_config_id)
        llm_params = ((merged.get("llm") or {}).get("params") or {}) if merged.get("llm") else {}
        embedder_params = (
            ((merged.get("embedder") or {}).get("params") or {}) if merged.get("embedder") else {}
        )
        a06.evidence = {
            "llm_base_url": llm_params.get("base_url"),
            "embedder_base_url": embedder_params.get("base_url"),
            "llm_has_api_key": bool(llm_params.get("api_key")),
            "embedder_has_api_key": bool(embedder_params.get("api_key")),
            "llm_endpoint_key_present": "endpoint_key" in llm_params,
            "embedder_endpoint_key_present": "endpoint_key" in embedder_params,
        }
        if (
            not llm_params.get("base_url")
            or not llm_params.get("api_key")
            or "endpoint_key" in llm_params
            or not embedder_params.get("base_url")
            or not embedder_params.get("api_key")
            or "endpoint_key" in embedder_params
        ):
            a06.status = "FAIL"
            a06.failure = build_failure(
                stage="provider_merge",
                location="run_real_suite.main",
                provider_model="settings::model_endpoints",
                raw_error="endpoint_merge_missing_or_endpoint_key_leaked",
            )
    except Exception as exc:
        a06.status = "FAIL"
        a06.failure = _failure_from_exc(
            stage="provider_merge",
            location="run_real_suite.main",
            provider_model="settings::model_endpoints",
            exc=exc,
        )
    cases.append(a06)

    main_bundle = _runtime_bundle(main_settings_path)
    ingester = main_bundle["ingester"]
    query_runner = main_bundle["query_runner"]
    eval_runner = main_bundle["eval_runner"]
    admin_runner = main_bundle["admin_runner"]
    sqlite = main_bundle["sqlite"]

    missing_strategy_evidence: dict[str, Any] = {}
    missing_strategy_failure: FailureInfo | None = None
    try:
        query_runner.run("hello", strategy_config_id="local.missing_strategy", top_k=3)
        missing_strategy_failure = build_failure(
            stage="strategy_loader",
            location="run_real_suite.main",
            provider_model="strategy::loader",
            raw_error="expected_missing_strategy_error",
        )
    except Exception as exc:
        missing_strategy_evidence = {
            "query": "hello",
            "invalid_strategy": "local.missing_strategy",
            "error_type": type(exc).__name__,
        }
        missing_strategy_failure = build_failure(
            stage="strategy_loader",
            location="run_real_suite.main",
            provider_model="strategy::loader",
            raw_error=str(exc),
        )

    a04 = _case("A-04", "strategy 文件不存在", "settings + strategy loader", strategy_config_id)
    a04.status = (
        "PASS"
        if missing_strategy_failure is not None
        and "strategy config not found" in str(missing_strategy_failure.raw_error or "")
        else "FAIL"
    )
    a04.evidence = missing_strategy_evidence
    if missing_strategy_failure is not None:
        a04.failure = missing_strategy_failure
    cases.append(a04)

    # B. CLI 摄取
    ingest_plan = [
        ("B-01", "simple", "simple.pdf"),
        ("B-02", "with_images", "with_images.pdf"),
        ("B-03", "complex", "complex_technical_doc.pdf"),
        ("B-04", "zh_technical", "chinese_technical_doc.pdf"),
        ("B-05", "zh_long", "chinese_long_doc.pdf"),
        ("B-06", "blogger", "blogger_intro.pdf"),
    ]
    for case_id, alias, filename in ingest_plan:
        case = _case(case_id, f"摄取 {filename}", "CLI 摄取", strategy_config_id)
        try:
            resp = ingester.run(
                fixture_path(filename), strategy_config_id=strategy_config_id, policy="new_version"
            )
            structured = dict(resp.structured or {})
            counts = structured.get("counts") or {}
            asset_stage_spans: list[str] = []
            asset_ids: list[str] = []
            caption_count = 0
            caption_samples: list[str] = []
            vision_snippet_count = 0
            enricher_provider_id = ""
            if case_id == "B-02":
                spans = getattr(resp.trace, "spans", None) or []
                asset_stage_spans = [
                    str(getattr(span, "name", ""))
                    for span in spans
                    if str(getattr(span, "name", ""))
                    in {"asset_normalize", "section_assets", "transform_post", "upsert"}
                ]
                asset_ids = sqlite.fetch_asset_ids_by_doc_version(
                    doc_id=str(structured.get("doc_id") or ""),
                    version_id=str(structured.get("version_id") or ""),
                )
                if asset_ids:
                    enrich_assets = sqlite.fetch_asset_enrichments(asset_ids)
                    caption_samples = [
                        str((item.get("caption_text") or "")).strip()
                        for item in enrich_assets.values()
                        if str((item.get("caption_text") or "")).strip()
                    ][:3]
                    caption_count = len(caption_samples)
                with sqlite._connect() as conn:
                    chunk_rows = conn.execute(
                        (
                            "SELECT chunk_id FROM chunks "
                            "WHERE doc_id=? AND version_id=? "
                            "ORDER BY chunk_index"
                        ),
                        (structured.get("doc_id"), structured.get("version_id")),
                    ).fetchall()
                chunk_ids = [str(row["chunk_id"]) for row in chunk_rows if row["chunk_id"]]
                if chunk_ids:
                    chunk_enrich = sqlite.fetch_chunk_enrichments(chunk_ids)
                    vision_snippet_count = sum(
                        1
                        for item in chunk_enrich.values()
                        if str(item.get("vision_snippets_json") or "").strip()
                    )
                merged = merged_provider_specs(main_settings, strategy_config_id)
                enricher_provider_id = str(
                    ((merged.get("enricher") or {}).get("provider_id") or "")
                )
            case.evidence = {
                "file": filename,
                "trace_id": resp.trace_id,
                "doc_id": structured.get("doc_id"),
                "version_id": structured.get("version_id"),
                "status": structured.get("status"),
                "chunks_written": counts.get("chunks_written", 0),
                "assets_written": counts.get("assets_written", 0),
                "asset_stage_spans": asset_stage_spans,
                "asset_ref_count": len(asset_ids),
                "caption_count": caption_count,
                "caption_samples": caption_samples,
                "vision_snippet_count": vision_snippet_count,
                "enricher_provider_id": enricher_provider_id,
            }
            if structured.get("status") not in {"ok", "skipped"}:
                case.status = "FAIL"
                case.failure = build_failure(
                    stage="ingest",
                    location="run_real_suite.main",
                    provider_model="ingest::pipeline",
                    raw_error=str(structured.get("error") or "ingest_failed"),
                )
            else:
                evidence["doc_ids_active"].append(structured.get("doc_id"))
                evidence["doc_ids_by_alias"][alias] = structured.get("doc_id")
                evidence["trace_ids"].append(resp.trace_id)
                evidence["ingest_trace_ids"].append(resp.trace_id)
                if alias == "with_images":
                    evidence["images_doc_id"] = structured.get("doc_id")
                if case_id == "B-02" and counts.get("assets_written", 0) <= 0:
                    case.status = "FAIL"
                    case.failure = build_failure(
                        stage="ingest_validation",
                        location="run_real_suite.main",
                        provider_model="ingest::pipeline",
                        raw_error="expected_assets_written>0",
                    )
                if case_id == "B-02" and not asset_ids:
                    case.status = "FAIL"
                    case.failure = build_failure(
                        stage="ingest_validation",
                        location="run_real_suite.main",
                        provider_model="ingest::pipeline",
                        raw_error="expected_asset_refs_for_with_images",
                    )
                if case_id == "B-02" and not {
                    "asset_normalize",
                    "section_assets",
                    "transform_post",
                    "upsert",
                }.issubset(set(asset_stage_spans)):
                    case.status = "FAIL"
                    case.failure = build_failure(
                        stage="ingest_validation",
                        location="run_real_suite.main",
                        provider_model="trace::ingest",
                        raw_error="missing_asset_stage_spans",
                    )
                if (
                    case_id == "B-02"
                    and enricher_provider_id != "noop"
                    and caption_count <= 0
                    and vision_snippet_count <= 0
                ):
                    case.status = "FAIL"
                    case.failure = build_failure(
                        stage="ingest_validation",
                        location="run_real_suite.main",
                        provider_model=f"enricher::{enricher_provider_id}",
                        raw_error="expected_caption_or_vision_snippets_for_image_doc",
                    )
                if case_id != "B-02" and counts.get("chunks_written", 0) <= 0:
                    case.status = "FAIL"
                    case.failure = build_failure(
                        stage="ingest_validation",
                        location="run_real_suite.main",
                        provider_model="ingest::pipeline",
                        raw_error="expected_chunks_written>0",
                    )
        except Exception as exc:
            case.status = "FAIL"
            case.failure = _failure_from_exc(
                stage="ingest",
                location="run_real_suite.main",
                provider_model="ingest::pipeline",
                exc=exc,
            )
        cases.append(case)

    b07 = _case("B-07", "摄取 sample.txt 返回清晰类型错误", "CLI 摄取", strategy_config_id)
    try:
        txt_resp = ingester.run(
            fixture_path("sample.txt"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        structured = dict(txt_resp.structured or {})
        b07.evidence = {
            "file": "sample.txt",
            "trace_id": txt_resp.trace_id,
            "status": structured.get("status"),
            "error": structured.get("error") or structured.get("reason"),
        }
        if not (
            structured.get("status") == "error"
            and "unsupported file type" in str(structured.get("error") or "")
        ):
            b07.status = "FAIL"
            b07.failure = build_failure(
                stage="ingest_validation",
                location="run_real_suite.main",
                provider_model="loader::dispatch",
                raw_error="sample_txt_should_be_rejected",
            )
    except Exception as exc:
        b07.status = "FAIL"
        b07.failure = _failure_from_exc(
            stage="ingest_validation",
            location="run_real_suite.main",
            provider_model="loader::dispatch",
            exc=exc,
        )
    cases.append(b07)

    b08 = _case("B-08", "重复摄取同一文件幂等", "CLI 摄取", strategy_config_id)
    try:
        idem = ingester.run(
            fixture_path("simple.pdf"), strategy_config_id=strategy_config_id, policy="skip"
        )
        structured = dict(idem.structured or {})
        b08.evidence = {
            "file": "simple.pdf",
            "trace_id": idem.trace_id,
            "status": structured.get("status"),
            "decision": structured.get("decision"),
            "doc_id": structured.get("doc_id"),
        }
        if structured.get("status") != "skipped":
            b08.status = "FAIL"
            b08.failure = build_failure(
                stage="ingest_idempotency",
                location="run_real_suite.main",
                provider_model="ingest::pipeline",
                raw_error="expected_skipped_status",
            )
    except Exception as exc:
        b08.status = "FAIL"
        b08.failure = _failure_from_exc(
            stage="ingest_idempotency",
            location="run_real_suite.main",
            provider_model="ingest::pipeline",
            exc=exc,
        )
    cases.append(b08)

    b09 = _case("B-09", "隔离运行摄取不污染主库", "CLI 摄取", strategy_config_id)
    try:
        iso_settings = _make_settings(
            run_id=run_id,
            suffix="ingest-isolated",
            strategy_config_id="local.default",
        )
        iso_doc = iso_settings.parent / f"qa-plus-isolated-{run_id}.md"
        iso_doc.write_text(
            "# QA Plus Isolated\n\nThis markdown exists only for isolated ingest.\n",
            encoding="utf-8",
        )
        iso_bundle = _runtime_bundle(iso_settings)
        iso_ingest = iso_bundle["ingester"].run(
            iso_doc, strategy_config_id="local.default", policy="new_version"
        )
        iso_structured = dict(iso_ingest.structured or {})
        main_client = _dashboard_client(main_settings_path)
        iso_client = _dashboard_client(iso_settings)
        main_doc_ids = {
            item.get("doc_id")
            for item in (
                main_client.get("/api/documents?limit=200&offset=0").json().get("items")
                or []
            )
        }
        iso_doc_ids = {
            item.get("doc_id")
            for item in (
                iso_client.get("/api/documents?limit=200&offset=0").json().get("items")
                or []
            )
        }
        iso_doc_id = iso_structured.get("doc_id")
        b09.evidence = {
            "isolated_doc_id": iso_doc_id,
            "main_has_doc": iso_doc_id in main_doc_ids,
            "isolated_has_doc": iso_doc_id in iso_doc_ids,
        }
        if not (
            iso_structured.get("status") == "ok"
            and iso_doc_id in iso_doc_ids
            and iso_doc_id not in main_doc_ids
        ):
            b09.status = "FAIL"
            b09.failure = build_failure(
                stage="isolated_ingest",
                location="run_real_suite.main",
                provider_model="ingest::pipeline",
                raw_error="isolated_run_visibility_mismatch",
            )
    except Exception as exc:
        b09.status = "FAIL"
        b09.failure = _failure_from_exc(
            stage="isolated_ingest",
            location="run_real_suite.main",
            provider_model="ingest::pipeline",
            exc=exc,
        )
    cases.append(b09)

    broken_embedder_strategy = strategy_path_for(run_id, "broken-embedder")
    write_strategy_yaml(
        broken_embedder_strategy,
        base_strategy_id="local.default",
        raw_override={
            "providers": {
                "embedder": {
                    "provider_id": "openai_compatible",
                    "params": {
                        "model": "text-embedding-v3",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "qa-plus-key",
                        "timeout_s": 1,
                    },
                }
            }
        },
    )
    broken_embedder_strategy_id = str(broken_embedder_strategy)

    b10 = _case("B-10", "摄取失败时 trace 落库", "CLI 摄取", broken_embedder_strategy_id)
    try:
        broken_ingest_settings = _make_settings(
            run_id=run_id,
            suffix="ingest-failure",
            strategy_config_id=broken_embedder_strategy_id,
        )
        broken_doc = broken_ingest_settings.parent / f"qa-plus-broken-ingest-{run_id}.md"
        broken_doc.write_text(
            "# Broken Ingest\n\nThis markdown should fail at embedding stage.\n",
            encoding="utf-8",
        )
        broken_bundle = _runtime_bundle(broken_ingest_settings)
        broken_resp = broken_bundle["ingester"].run(
            broken_doc,
            strategy_config_id=broken_embedder_strategy_id,
            policy="new_version",
        )
        trace_error = find_error_event(broken_resp.trace)
        b10.evidence = {
            "trace_id": broken_resp.trace_id,
            "status": (broken_resp.structured or {}).get("status"),
            "trace_error_event": trace_error,
        }
        if (
            (broken_resp.structured or {}).get("status") != "error"
            or not broken_resp.trace_id
            or trace_error is None
        ):
            b10.status = "FAIL"
            b10.failure = build_failure(
                stage="ingest_failure_trace",
                location="run_real_suite.main",
                provider_model="embedder::openai_compatible",
                raw_error=str((broken_resp.structured or {}).get("error") or "missing_trace_error"),
            )
    except Exception as exc:
        b10.status = "FAIL"
        b10.failure = _failure_from_exc(
            stage="ingest_failure_trace",
            location="run_real_suite.main",
            provider_model="embedder::openai_compatible",
            exc=exc,
        )
    cases.append(b10)

    b11 = _case("B-11", "摄取不存在路径返回清晰错误", "CLI 摄取", strategy_config_id)
    try:
        missing_path = fixture_path("__missing_document__.pdf")
        missing_resp = ingester.run(
            missing_path,
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        structured = dict(missing_resp.structured or {})
        b11.evidence = {
            "file": str(missing_path),
            "trace_id": missing_resp.trace_id,
            "status": structured.get("status"),
            "reason": structured.get("reason"),
            "file_path": structured.get("file_path"),
        }
        if not (
            structured.get("status") == "error"
            and structured.get("reason") == "file_not_found"
            and str(structured.get("file_path") or "").endswith("__missing_document__.pdf")
        ):
            b11.status = "FAIL"
            b11.failure = build_failure(
                stage="ingest_missing_path",
                location="run_real_suite.main",
                provider_model="ingest::runner",
                raw_error="missing_path_should_return_file_not_found",
            )
    except Exception as exc:
        b11.status = "FAIL"
        b11.failure = _failure_from_exc(
            stage="ingest_missing_path",
            location="run_real_suite.main",
            provider_model="ingest::runner",
            exc=exc,
        )
    cases.append(b11)

    b12 = _case("B-12", "ingest --verbose 输出详情", "CLI 摄取脚本", strategy_config_id)
    try:
        cli_ingest = _run_ingest_cli(
            file_path=fixture_path("simple.pdf"),
            strategy_config_id=strategy_config_id,
            policy="skip",
            settings_path=main_settings_path,
            verbose=True,
        )
        verbose_body = cli_ingest.get("verbose") or {}
        b12.evidence = {
            "trace_id": cli_ingest.get("trace_id"),
            "verbose_keys": sorted(verbose_body.keys()),
            "status": verbose_body.get("status"),
        }
        required_keys = {
            "file_path",
            "strategy_config_id",
            "policy",
            "trace_id",
            "status",
            "structured",
            "providers",
            "aggregates",
            "spans",
        }
        structured = verbose_body.get("structured") or {}
        if not (
            "=== VERBOSE DETAILS BEGIN ===" in str(cli_ingest.get("stdout") or "")
            and "=== VERBOSE DETAILS END ===" in str(cli_ingest.get("stdout") or "")
            and required_keys.issubset(set(verbose_body.keys()))
            and cli_ingest.get("trace_id")
            and (
                structured.get("doc_id")
                or structured.get("version_id")
                or structured.get("status") == "skipped"
            )
        ):
            b12.status = "FAIL"
            b12.failure = build_failure(
                stage="ingest_cli",
                location="run_real_suite.main",
                provider_model="cli::dev_ingest",
                raw_error="verbose_output_missing_required_sections",
            )
    except Exception as exc:
        b12.status = "FAIL"
        b12.failure = _failure_from_exc(
            stage="ingest_cli",
            location="run_real_suite.main",
            provider_model="cli::dev_ingest",
            exc=exc,
        )
    cases.append(b12)

    # C. CLI 查询与 Trace
    relevant_query = "Transformer 注意力机制是什么"
    relevant_resp = None
    c01 = _case("C-01", "基础检索命中", "CLI 查询", strategy_config_id)
    c02 = _case("C-02", "查询 trace 可读取", "CLI 查询 + Trace", strategy_config_id)
    c03 = _case("C-03", "Dense/Sparse 证据存在", "CLI 查询 + Trace", strategy_config_id)
    c04 = _case("C-04", "生成阶段事件存在", "CLI 查询 + Trace", strategy_config_id)
    try:
        relevant_resp = query_runner.run(
            relevant_query, strategy_config_id=strategy_config_id, top_k=args.top_k
        )
        top_source = relevant_resp.sources[0] if relevant_resp.sources else None
        common_evidence = {
            "query": relevant_query,
            "trace_id": relevant_resp.trace_id,
            "top_chunk_id": top_source.chunk_id if top_source else None,
            "top_doc_id": top_source.doc_id if top_source else None,
            "source_count": len(relevant_resp.sources),
        }
        if top_source is not None:
            evidence["sample_chunk_id"] = top_source.chunk_id
        evidence["query_trace_id"] = relevant_resp.trace_id
        evidence["trace_ids"].append(relevant_resp.trace_id)

        c01.evidence = common_evidence
        if not relevant_resp.sources:
            c01.status = "FAIL"
            c01.failure = build_failure(
                stage="query",
                location="run_real_suite.main",
                provider_model="query::pipeline",
                raw_error="query_empty_sources",
            )

        c02.evidence = {
            "trace_id": relevant_resp.trace_id,
            "trace_present": bool(relevant_resp.trace),
        }
        if not relevant_resp.trace_id or relevant_resp.trace is None:
            c02.status = "FAIL"
            c02.failure = build_failure(
                stage="query_trace",
                location="run_real_suite.main",
                provider_model="query::trace",
                raw_error="trace_missing",
            )

        c03.evidence = {
            "trace_id": relevant_resp.trace_id,
            "has_dense": traces_have_event(relevant_resp.trace, "retrieve_dense", "retrieval"),
            "has_sparse": traces_have_event(relevant_resp.trace, "retrieve_sparse", "retrieval"),
        }
        if not (c03.evidence["has_dense"] and c03.evidence["has_sparse"]):
            c03.status = "FAIL"
            c03.failure = build_failure(
                stage="query_trace",
                location="run_real_suite.main",
                provider_model="query::retrieval",
                raw_error="dense_or_sparse_event_missing",
            )

        c04.evidence = {
            "trace_id": relevant_resp.trace_id,
            "has_generate_used": traces_have_event(relevant_resp.trace, "generate", "generate."),
            "has_generate_fallback": traces_have_event(
                relevant_resp.trace, "generate", "warn.generate_fallback"
            ),
        }
        if not (c04.evidence["has_generate_used"] or c04.evidence["has_generate_fallback"]):
            c04.status = "FAIL"
            c04.failure = build_failure(
                stage="query_trace",
                location="run_real_suite.main",
                provider_model="query::generate",
                raw_error="generate_event_missing",
            )
    except Exception as exc:
        for case in (c01, c02, c03, c04):
            case.status = "FAIL"
            case.failure = _failure_from_exc(
                stage="query",
                location="run_real_suite.main",
                provider_model="query::pipeline",
                exc=exc,
            )
    cases.extend([c01, c02, c03, c04])

    c05 = _case("C-05", "中文查询命中中文文档", "CLI 查询", strategy_config_id)
    try:
        zh_resp = query_runner.run(
            "什么是混合检索和 BM25",
            strategy_config_id=strategy_config_id,
            top_k=3,
        )
        top_doc_id = zh_resp.sources[0].doc_id if zh_resp.sources else None
        valid_doc_ids = {
            evidence["doc_ids_by_alias"].get("zh_technical"),
            evidence["doc_ids_by_alias"].get("zh_long"),
        }
        c05.evidence = {
            "query": "什么是混合检索和 BM25",
            "top_doc_id": top_doc_id,
            "valid_doc_ids": sorted([str(v) for v in valid_doc_ids if v]),
        }
        if top_doc_id not in valid_doc_ids:
            c05.status = "FAIL"
            c05.failure = build_failure(
                stage="query_validation",
                location="run_real_suite.main",
                provider_model="query::pipeline",
                raw_error="top_result_not_chinese_doc",
            )
    except Exception as exc:
        c05.status = "FAIL"
        c05.failure = _failure_from_exc(
            stage="query_validation",
            location="run_real_suite.main",
            provider_model="query::pipeline",
            exc=exc,
        )
    cases.append(c05)

    c06 = _case("C-06", "空查询处理清晰", "CLI 查询", strategy_config_id)
    try:
        empty_resp = query_runner.run(
            "   ",
            strategy_config_id=strategy_config_id,
            top_k=5,
        )
        c06.evidence = {
            "query": "   ",
            "trace_id": empty_resp.trace_id,
            "source_count": len(empty_resp.sources),
            "content_md": empty_resp.content_md,
        }
        if not (
            empty_resp.trace_id
            and not empty_resp.sources
            and "（空查询）请提供一个问题。" in str(empty_resp.content_md or "")
        ):
            c06.status = "FAIL"
            c06.failure = build_failure(
                stage="query_validation",
                location="run_real_suite.main",
                provider_model="query::pipeline",
                raw_error="empty_query_should_return_prompt_without_sources",
            )
    except Exception as exc:
        c06.status = "FAIL"
        c06.failure = _failure_from_exc(
            stage="query_validation",
            location="run_real_suite.main",
            provider_model="query::pipeline",
            exc=exc,
        )
    cases.append(c06)

    c07 = _case("C-07", "长查询处理稳定", "CLI 查询", strategy_config_id)
    try:
        long_query = (
            "Transformer 模型中的自注意力机制如何工作，包括 Multi-Head Attention 和 "
            "RoPE 位置编码的原理，以及 KV Cache 优化策略。同时请解释 RAG 系统中混合检索的工作流程，"
            "包括 Dense Retrieval、BM25 Sparse Retrieval 和 RRF 融合算法的具体实现方式。"
            "还有 Cross-Encoder Reranker 和 LLM Reranker 的对比分析，以及在生产环境中如何选择"
            "合适的向量数据库（如 ChromaDB、FAISS、Milvus）来存储和检索 Embedding 向量。"
            "请详细说明每个组件的优缺点和适用场景。"
        )
        long_resp = query_runner.run(long_query, strategy_config_id=strategy_config_id, top_k=3)
        c07.evidence = {
            "query_len": len(long_query),
            "trace_id": long_resp.trace_id,
            "source_count": len(long_resp.sources),
        }
        if not long_resp.trace_id:
            c07.status = "FAIL"
            c07.failure = build_failure(
                stage="query_long",
                location="run_real_suite.main",
                provider_model="query::pipeline",
                raw_error="missing_trace_id",
            )
    except Exception as exc:
        c07.status = "FAIL"
        c07.failure = _failure_from_exc(
            stage="query_long",
            location="run_real_suite.main",
            provider_model="query::pipeline",
            exc=exc,
        )
    cases.append(c07)

    c08 = _case("C-08", "无关查询低相关或空结果", "CLI 查询", strategy_config_id)
    try:
        unrelated_query = "zzqvxxp cosmic-hypergraph ordinance 99173"
        unrelated_resp = query_runner.run(
            unrelated_query, strategy_config_id=strategy_config_id, top_k=3
        )
        relevant_top_score = (
            float(relevant_resp.sources[0].score)
            if relevant_resp is not None and relevant_resp.sources
            else None
        )
        unrelated_top_score = (
            float(unrelated_resp.sources[0].score) if unrelated_resp.sources else None
        )
        c08.evidence = {
            "query": unrelated_query,
            "source_count": len(unrelated_resp.sources),
            "top_score": unrelated_top_score,
            "relevant_top_score": relevant_top_score,
        }
        if (
            unrelated_resp.sources
            and relevant_top_score is not None
            and unrelated_top_score is not None
        ):
            if unrelated_top_score >= relevant_top_score:
                c08.status = "FAIL"
                c08.failure = build_failure(
                    stage="query_validation",
                    location="run_real_suite.main",
                    provider_model="query::pipeline",
                    raw_error="unrelated_query_scored_too_high",
                )
    except Exception as exc:
        c08.status = "FAIL"
        c08.failure = _failure_from_exc(
            stage="query_validation",
            location="run_real_suite.main",
            provider_model="query::pipeline",
            exc=exc,
        )
    cases.append(c08)

    c09 = _case("C-09", "查询失败时错误链路完整", "CLI 查询", broken_embedder_strategy_id)
    broken_query_failure: FailureInfo | None = None
    try:
        broken_query_settings = _make_settings(
            run_id=run_id,
            suffix="query-failure",
            strategy_config_id=broken_embedder_strategy_id,
        )
        broken_query_bundle = _runtime_bundle(broken_query_settings)
        broken_query_bundle["query_runner"].run(
            "hello world",
            strategy_config_id=broken_embedder_strategy_id,
            top_k=3,
        )
        c09.status = "FAIL"
        broken_query_failure = build_failure(
            stage="query_failure",
            location="run_real_suite.main",
            provider_model="embedder::openai_compatible",
            raw_error="expected_query_failure",
        )
    except Exception as exc:
        broken_query_failure = _failure_from_exc(
            stage="retrieve_dense",
            location="run_real_suite.main",
            provider_model="embedder::openai_compatible::text-embedding-v3",
            exc=exc,
        )
        c09.evidence = {
            "query": "hello world",
            "error_type": type(exc).__name__,
        }
        c09.failure = broken_query_failure
        c09.status = (
            "PASS"
            if broken_query_failure.stage
            and broken_query_failure.location
            and broken_query_failure.provider_model
            and broken_query_failure.raw_error
            else "FAIL"
        )
    if c09.status != "PASS" and broken_query_failure is not None:
        c09.failure = broken_query_failure
    cases.append(c09)

    c10 = _case("C-10", "query top_k 参数生效", "CLI 查询脚本", strategy_config_id)
    try:
        cli_topk = _run_query_cli(
            query=relevant_query,
            strategy_config_id=strategy_config_id,
            top_k=2,
            settings_path=main_settings_path,
            verbose=True,
        )
        verbose_body = cli_topk.get("verbose") or {}
        sources = verbose_body.get("sources") or []
        c10.evidence = {
            "trace_id": cli_topk.get("trace_id"),
            "top_k": verbose_body.get("top_k"),
            "source_count": verbose_body.get("source_count"),
            "sources": sources,
        }
        if not (
            verbose_body.get("top_k") == 2
            and int(verbose_body.get("source_count") or 0) <= 2
            and cli_topk.get("trace_id")
            and all(
                item.get("chunk_id")
                and item.get("doc_id")
                and item.get("score") is not None
                and item.get("source")
                and item.get("section_path")
                for item in sources
            )
        ):
            c10.status = "FAIL"
            c10.failure = build_failure(
                stage="query_cli",
                location="run_real_suite.main",
                provider_model="cli::dev_query",
                raw_error="top_k_parameter_not_reflected_in_verbose_output",
            )
    except Exception as exc:
        c10.status = "FAIL"
        c10.failure = _failure_from_exc(
            stage="query_cli",
            location="run_real_suite.main",
            provider_model="cli::dev_query",
            exc=exc,
        )
    cases.append(c10)

    c11 = _case("C-11", "query --verbose 输出检索详情", "CLI 查询脚本", strategy_config_id)
    try:
        cli_verbose = _run_query_cli(
            query=relevant_query,
            strategy_config_id=strategy_config_id,
            top_k=5,
            settings_path=main_settings_path,
            verbose=True,
        )
        verbose_body = cli_verbose.get("verbose") or {}
        c11.evidence = {
            "trace_id": cli_verbose.get("trace_id"),
            "verbose_keys": sorted(verbose_body.keys()),
            "source_count": verbose_body.get("source_count"),
            "span_names": [
                item.get("span")
                for item in (verbose_body.get("spans") or [])
                if item.get("span")
            ][:10],
        }
        required_keys = {
            "query",
            "strategy_config_id",
            "top_k",
            "trace_id",
            "source_count",
            "sources",
            "providers",
            "aggregates",
            "spans",
        }
        if not (
            "=== VERBOSE DETAILS BEGIN ===" in str(cli_verbose.get("stdout") or "")
            and "=== VERBOSE DETAILS END ===" in str(cli_verbose.get("stdout") or "")
            and required_keys.issubset(set(verbose_body.keys()))
            and cli_verbose.get("trace_id")
        ):
            c11.status = "FAIL"
            c11.failure = build_failure(
                stage="query_cli",
                location="run_real_suite.main",
                provider_model="cli::dev_query",
                raw_error="verbose_output_missing_required_sections",
            )
    except Exception as exc:
        c11.status = "FAIL"
        c11.failure = _failure_from_exc(
            stage="query_cli",
            location="run_real_suite.main",
            provider_model="cli::dev_query",
            exc=exc,
        )
    cases.append(c11)

    # D. CLI 评估
    d01 = _case("D-01", "运行 rag_eval_small", "CLI 评估", strategy_config_id)
    eval_result = None
    try:
        eval_result = eval_runner.run(
            "rag_eval_small", strategy_config_id=strategy_config_id, top_k=args.top_k
        )
        metrics, nan_keys = safe_metric_dict(eval_result.metrics)
        d01.evidence = {
            "dataset_id": "rag_eval_small",
            "run_id": eval_result.run_id,
            "metrics": metrics,
            "nan_metrics": nan_keys,
        }
        evidence["eval_run_id"] = eval_result.run_id
        if not eval_result.run_id or not metrics:
            d01.status = "FAIL"
            d01.failure = build_failure(
                stage="eval",
                location="run_real_suite.main",
                provider_model="evaluator::pipeline",
                raw_error="eval_metrics_missing",
            )
    except Exception as exc:
        d01.status = "FAIL"
        d01.failure = _failure_from_exc(
            stage="eval",
            location="run_real_suite.main",
            provider_model="evaluator::pipeline",
            exc=exc,
        )
    cases.append(d01)

    d04 = _case("D-04", "评估失败诊断", "CLI 评估", strategy_config_id)
    d06 = _case("D-06", "评估失败仍保留 case 级 artifacts", "CLI 评估", strategy_config_id)
    try:
        broken_eval_settings = _make_settings(
            run_id=run_id,
            suffix="eval-failure",
            strategy_config_id=strategy_config_id,
            providers_override={
                "evaluator": {
                    "provider_id": "ragas",
                    "params": {
                        "model": "qwen-turbo",
                        "embedding_model": "text-embedding-v3",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "qa-plus-key",
                    },
                }
            },
        )
        broken_eval_bundle = _runtime_bundle(broken_eval_settings)
        broken_eval = broken_eval_bundle["eval_runner"].run(
            "rag_eval_small", strategy_config_id=strategy_config_id, top_k=args.top_k
        )
        first_case = broken_eval.cases[0] if broken_eval.cases else None
        first_artifacts = first_case.artifacts if first_case is not None else {}
        d04.evidence = {
            "run_id": broken_eval.run_id,
            "artifacts": first_artifacts,
        }
        d04.status = (
            "PASS"
            if first_artifacts.get("stage") and first_artifacts.get("model")
            else "FAIL"
        )
        if d04.status != "PASS":
            d04.failure = build_failure(
                stage="eval_diagnostics",
                location="run_real_suite.main",
                provider_model="evaluator::ragas",
                raw_error="missing_stage_or_model_in_artifacts",
            )

        rows = broken_eval_bundle["sqlite"].list_eval_case_results(run_id=broken_eval.run_id)
        first_row = rows[0] if rows else {}
        artifacts_json = json_loads_safe(first_row.get("artifacts_json"))
        d06.evidence = {
            "run_id": broken_eval.run_id,
            "persisted_artifacts": artifacts_json,
        }
        d06.status = (
            "PASS"
            if artifacts_json.get("stage") and artifacts_json.get("model")
            else "FAIL"
        )
        if d06.status != "PASS":
            d06.failure = build_failure(
                stage="eval_case_results",
                location="run_real_suite.main",
                provider_model="sqlite::eval_case_results",
                raw_error="persisted_artifacts_missing_stage_or_model",
            )
    except Exception as exc:
        for case in (d04, d06):
            case.status = "FAIL"
            case.failure = _failure_from_exc(
                stage="eval_diagnostics",
                location="run_real_suite.main",
                provider_model="evaluator::ragas",
                exc=exc,
            )
    cases.extend([d04, d06])

    d05 = _case("D-05", "使用 golden set 自定义数据集评估", "CLI 评估", strategy_config_id)
    try:
        golden_eval_settings = _make_settings(
            run_id=run_id,
            suffix="eval-golden",
            strategy_config_id=strategy_config_id,
            providers_override={
                "evaluator": {
                    "provider_id": "composite",
                    "params": {},
                },
                "judge": {
                    "provider_id": "noop",
                    "params": {},
                },
            },
        )
        golden_bundle = _runtime_bundle(golden_eval_settings)
        golden_bundle["ingester"].run(
            Path("DEV_SPEC.md"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        golden_cli = _run_eval_cli(
            dataset_id="tests/fixtures/golden_test_set.json",
            strategy_config_id=strategy_config_id,
            top_k=args.top_k,
            settings_path=golden_eval_settings,
            verbose=True,
        )
        golden_body = golden_cli.get("verbose") or {}
        golden_metrics = golden_body.get("metrics") or {}
        d05.evidence = {
            "dataset_id": golden_body.get("dataset_id"),
            "run_id": golden_body.get("run_id"),
            "metrics": golden_metrics,
        }
        if not (
            golden_body.get("dataset_id") == "golden_test_set"
            and golden_body.get("run_id")
            and golden_metrics
        ):
            d05.status = "FAIL"
            d05.failure = build_failure(
                stage="eval_dataset",
                location="run_real_suite.main",
                provider_model="evaluator::pipeline",
                raw_error="golden_dataset_not_applied_or_metrics_empty",
            )
    except Exception as exc:
        d05.status = "FAIL"
        d05.failure = _failure_from_exc(
            stage="eval_dataset",
            location="run_real_suite.main",
            provider_model="evaluator::pipeline",
            exc=exc,
        )
    cases.append(d05)

    d07 = _case(
        "D-07",
        "Cross-Encoder 策略评估链路可执行",
        "CLI 评估",
        "local.production_like_cross_encoder",
    )
    try:
        cross_eval = eval_runner.run(
            "rag_eval_small",
            strategy_config_id="local.production_like_cross_encoder",
            top_k=args.top_k,
        )
        cross_trace_id = cross_eval.cases[0].trace_id if cross_eval.cases else ""
        client = _dashboard_client(main_settings_path)
        trace_body = client.get(f"/api/trace/{cross_trace_id}").json() if cross_trace_id else {}
        reranker_provider = ((trace_body.get("trace") or {}).get("providers") or {}).get(
            "reranker"
        ) or {}
        d07.evidence = {
            "run_id": cross_eval.run_id,
            "first_trace_id": cross_trace_id,
            "reranker_provider_id": reranker_provider.get("provider_id"),
        }
        if reranker_provider.get("provider_id") != "cross_encoder":
            d07.status = "FAIL"
            d07.failure = build_failure(
                stage="cross_encoder_eval",
                location="run_real_suite.main",
                provider_model="reranker::cross_encoder",
                raw_error="cross_encoder_provider_not_observed",
            )
    except Exception as exc:
        d07.status = "FAIL"
        d07.failure = _failure_from_exc(
            stage="cross_encoder_eval",
            location="run_real_suite.main",
            provider_model="reranker::cross_encoder",
            exc=exc,
        )
    cases.append(d07)

    d08 = _case("D-08", "eval --verbose 输出详情", "CLI 评估脚本", strategy_config_id)
    try:
        cli_eval = _run_eval_cli(
            dataset_id="rag_eval_small",
            strategy_config_id=strategy_config_id,
            top_k=3,
            settings_path=main_settings_path,
            verbose=True,
        )
        verbose_body = cli_eval.get("verbose") or {}
        cases_body = verbose_body.get("cases") or []
        d08.evidence = {
            "verbose_keys": sorted(verbose_body.keys()),
            "run_id": verbose_body.get("run_id"),
            "case_count": len(cases_body),
        }
        required_keys = {
            "dataset_id",
            "strategy_config_id",
            "top_k",
            "run_id",
            "metrics",
            "cases",
        }
        if not (
            "=== VERBOSE DETAILS BEGIN ===" in str(cli_eval.get("stdout") or "")
            and "=== VERBOSE DETAILS END ===" in str(cli_eval.get("stdout") or "")
            and required_keys.issubset(set(verbose_body.keys()))
            and verbose_body.get("run_id")
            and all(item.get("case_id") and item.get("trace_id") for item in cases_body)
        ):
            d08.status = "FAIL"
            d08.failure = build_failure(
                stage="eval_cli",
                location="run_real_suite.main",
                provider_model="cli::dev_eval",
                raw_error="verbose_output_missing_required_sections",
            )
    except Exception as exc:
        d08.status = "FAIL"
        d08.failure = _failure_from_exc(
            stage="eval_cli",
            location="run_real_suite.main",
            provider_model="cli::dev_eval",
            exc=exc,
        )
    cases.append(d08)

    d09 = _case(
        "D-09",
        "使用 composite evaluator 进行 CLI 评估",
        "CLI 评估脚本",
        strategy_config_id,
    )
    try:
        composite_eval_settings = _make_settings(
            run_id=run_id,
            suffix="eval-composite",
            strategy_config_id=strategy_config_id,
            providers_override={
                "evaluator": {
                    "provider_id": "composite",
                    "params": {},
                },
                "judge": {
                    "provider_id": "noop",
                    "params": {},
                },
            },
        )
        composite_cli = _run_eval_cli(
            dataset_id="production_like_eval_smoke",
            strategy_config_id=strategy_config_id,
            top_k=3,
            settings_path=composite_eval_settings,
            verbose=True,
        )
        composite_body = composite_cli.get("verbose") or {}
        composite_metrics = composite_body.get("metrics") or {}
        composite_cases = composite_body.get("cases") or []
        d09.evidence = {
            "run_id": composite_body.get("run_id"),
            "metric_keys": sorted(composite_metrics.keys()),
            "case_count": len(composite_cases),
        }
        if not (
            composite_body.get("run_id")
            and {
                "retrieval.hit_rate@3",
                "retrieval.mrr",
                "retrieval.ndcg@3",
            }.issubset(set(composite_metrics.keys()))
            and all(item.get("case_id") and item.get("trace_id") for item in composite_cases)
        ):
            d09.status = "FAIL"
            d09.failure = build_failure(
                stage="eval_cli_composite",
                location="run_real_suite.main",
                provider_model="evaluator::composite",
                raw_error="composite_eval_metrics_or_cases_missing",
            )
    except Exception as exc:
        d09.status = "FAIL"
        d09.failure = _failure_from_exc(
            stage="eval_cli_composite",
            location="run_real_suite.main",
            provider_model="evaluator::composite",
            exc=exc,
        )
    cases.append(d09)

    d10 = _case("D-10", "使用 ragas evaluator 进行 CLI 评估", "CLI 评估脚本", strategy_config_id)
    try:
        ragas_eval_settings = _make_settings(
            run_id=run_id,
            suffix="eval-ragas",
            strategy_config_id=strategy_config_id,
            providers_override={
                "evaluator": {
                    "provider_id": "ragas",
                    "params": {
                        "endpoint_key": "qwen",
                        "model": "qwen-turbo",
                        "embedding_model": "text-embedding-v3",
                    },
                },
            },
        )
        ragas_cli = _run_eval_cli(
            dataset_id="production_like_eval_smoke",
            strategy_config_id=strategy_config_id,
            top_k=3,
            settings_path=ragas_eval_settings,
            verbose=True,
        )
        ragas_body = ragas_cli.get("verbose") or {}
        ragas_metrics = ragas_body.get("metrics") or {}
        ragas_cases = ragas_body.get("cases") or []
        d10.evidence = {
            "run_id": ragas_body.get("run_id"),
            "metric_keys": sorted(ragas_metrics.keys()),
            "case_count": len(ragas_cases),
        }
        if not (
            ragas_body.get("run_id")
            and {"ragas.faithfulness", "ragas.answer_relevancy"}.issubset(
                set(ragas_metrics.keys())
            )
            and all(item.get("case_id") and item.get("trace_id") for item in ragas_cases)
        ):
            d10.status = "FAIL"
            d10.failure = build_failure(
                stage="eval_cli_ragas",
                location="run_real_suite.main",
                provider_model="evaluator::ragas",
                raw_error="ragas_eval_metrics_or_cases_missing",
            )
    except Exception as exc:
        d10.status = "FAIL"
        d10.failure = _failure_from_exc(
            stage="eval_cli_ragas",
            location="run_real_suite.main",
            provider_model="evaluator::ragas",
            exc=exc,
        )
    cases.append(d10)

    # E / D dashboard 读取
    client = _dashboard_client(main_settings_path)
    overview_body = client.get("/api/overview").json()
    docs_body = client.get("/api/documents?limit=100&offset=0").json()
    eval_runs_body = client.get("/api/eval/runs?limit=50&offset=0").json()
    eval_trends_body = client.get("/api/eval/trends?metric=hit_rate@k&window=30").json()

    d02 = _case("D-02", "评估历史可读", "CLI 评估 + Dashboard API", strategy_config_id)
    eval_run_ids = {item.get("run_id") for item in (eval_runs_body.get("items") or [])}
    d02.evidence = {
        "run_id": evidence.get("eval_run_id"),
        "visible_run_ids": sorted([str(v) for v in eval_run_ids if v])[:10],
    }
    if evidence.get("eval_run_id") not in eval_run_ids:
        d02.status = "FAIL"
        d02.failure = build_failure(
            stage="dashboard_eval_runs",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="eval_run_not_visible",
        )
    cases.append(d02)

    d03 = _case("D-03", "评估趋势可读", "CLI 评估 + Dashboard API", strategy_config_id)
    trend_points = eval_trends_body.get("points") or []
    d03.evidence = {
        "metric": eval_trends_body.get("metric"),
        "trend_points": len(trend_points),
    }
    if len(trend_points) < 1:
        d03.status = "FAIL"
        d03.failure = build_failure(
            stage="dashboard_eval_trends",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="trend_points_empty",
        )
    cases.append(d03)

    dash_payload = run_dashboard_checks(main_settings_path, evidence)

    e01 = _case("E-01", "Overview 文档/分块统计一致", "Dashboard API", strategy_config_id)
    e01.evidence = dash_payload["checks"].get("overview", {})
    if dash_payload["checks"].get("overview", {}).get("status") != "PASS":
        e01.status = "FAIL"
        e01.failure = build_failure(
            stage="dashboard_overview",
            location="check_dashboard_consistency.run_dashboard_checks",
            provider_model="dashboard::api",
            raw_error="overview_mismatch",
        )
    cases.append(e01)

    e02 = _case("E-02", "Overview provider 信息可读", "Dashboard API", strategy_config_id)
    providers = overview_body.get("providers") or {}
    e02.evidence = {"provider_keys": sorted(providers.keys())}
    if not providers:
        e02.status = "FAIL"
        e02.failure = build_failure(
            stage="dashboard_overview",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="providers_empty",
        )
    cases.append(e02)

    e03 = _case("E-03", "Browser 文档列表一致", "Dashboard API", strategy_config_id)
    doc_items = docs_body.get("items") or []
    doc_ids = {item.get("doc_id") for item in doc_items}
    expected_doc_ids = set(evidence.get("doc_ids_active") or [])
    e03.evidence = {
        "active_doc_ids": sorted([str(v) for v in doc_ids if v]),
        "expected_doc_ids": sorted([str(v) for v in expected_doc_ids if v]),
    }
    if not expected_doc_ids.issubset(doc_ids):
        e03.status = "FAIL"
        e03.failure = build_failure(
            stage="dashboard_documents",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="documents_missing_from_browser",
        )
    cases.append(e03)

    e04 = _case("E-04", "Chunk 详情一致", "Dashboard API", strategy_config_id)
    try:
        chunk_id = evidence.get("sample_chunk_id")
        chunk_body = client.get(f"/api/chunk/{chunk_id}").json() if chunk_id else {}
        e04.evidence = {
            "chunk_id": chunk_body.get("chunk_id"),
            "asset_count": len(chunk_body.get("asset_ids") or []),
            "text_len": len(str(chunk_body.get("chunk_text") or "")),
        }
        if not chunk_id or chunk_body.get("chunk_id") != chunk_id:
            e04.status = "FAIL"
            e04.failure = build_failure(
                stage="dashboard_chunk",
                location="run_real_suite.main",
                provider_model="dashboard::api",
                raw_error="chunk_detail_mismatch",
            )
    except Exception as exc:
        e04.status = "FAIL"
        e04.failure = _failure_from_exc(
            stage="dashboard_chunk",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            exc=exc,
        )
    cases.append(e04)

    e05 = _case("E-05", "Ingestion Trace 列表可见", "Dashboard API", strategy_config_id)
    ingest_traces = client.get("/api/traces?trace_type=ingestion&limit=200&offset=0").json().get(
        "items"
    ) or []
    ingest_trace_ids = {item.get("trace_id") for item in ingest_traces}
    expected_ingest_trace_ids = set(evidence.get("ingest_trace_ids") or [])
    e05.evidence = {
        "expected_trace_ids": sorted([str(v) for v in expected_ingest_trace_ids if v]),
        "visible_trace_ids": sorted([str(v) for v in ingest_trace_ids if v])[:20],
    }
    if not expected_ingest_trace_ids.issubset(ingest_trace_ids):
        e05.status = "FAIL"
        e05.failure = build_failure(
            stage="dashboard_traces",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="ingestion_trace_not_visible",
        )
    cases.append(e05)

    e06 = _case("E-06", "Query Trace 列表可见", "Dashboard API", strategy_config_id)
    query_traces = client.get("/api/traces?trace_type=query&limit=200&offset=0").json().get(
        "items"
    ) or []
    query_trace_ids = {item.get("trace_id") for item in query_traces}
    e06.evidence = {
        "query_trace_id": evidence.get("query_trace_id"),
        "visible_trace_ids": sorted([str(v) for v in query_trace_ids if v])[:20],
    }
    if evidence.get("query_trace_id") not in query_trace_ids:
        e06.status = "FAIL"
        e06.failure = build_failure(
            stage="dashboard_traces",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="query_trace_not_visible",
        )
    cases.append(e06)

    e07 = _case("E-07", "Eval 历史可见", "Dashboard API", strategy_config_id)
    e07.evidence = {
        "run_id": evidence.get("eval_run_id"),
        "run_visible": evidence.get("eval_run_id") in eval_run_ids,
        "trend_points": len(trend_points),
    }
    if not (e07.evidence["run_visible"] and len(trend_points) >= 1):
        e07.status = "FAIL"
        e07.failure = build_failure(
            stage="dashboard_eval",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="eval_history_or_trend_mismatch",
        )
    cases.append(e07)

    # F. MCP stdio
    f_payload = _run_mcp_stdio(main_settings_path)
    f01 = _case("F-01", "`tools/list` 返回关键工具", "MCP stdio", strategy_config_id)
    f01.status = f_payload["tools_list"]["status"]
    f01.evidence = f_payload["tools_list"]
    cases.append(f01)

    f02 = _case("F-02", "`library_ingest` 可写入隔离库", "MCP stdio", strategy_config_id)
    f02.status = f_payload["ingest"]["status"]
    f02.evidence = f_payload["ingest"]
    cases.append(f02)

    f03 = _case("F-03", "`library_query` 可返回结果", "MCP stdio", strategy_config_id)
    f03.status = f_payload["query"]["status"]
    f03.evidence = f_payload["query"]
    cases.append(f03)

    f04 = _case("F-04", "`library_get_document` 返回文档详情", "MCP stdio", strategy_config_id)
    f04.status = f_payload["get_document"]["status"]
    f04.evidence = f_payload["get_document"]
    cases.append(f04)

    f05 = _case("F-05", "`library_summarize_document` 返回摘要", "MCP stdio", strategy_config_id)
    f05.status = f_payload["summarize_document"]["status"]
    f05.evidence = f_payload["summarize_document"]
    cases.append(f05)

    f06 = _case("F-06", "`library_list_documents` 可读到文档", "MCP stdio", strategy_config_id)
    f06.status = f_payload["list_documents"]["status"]
    f06.evidence = f_payload["list_documents"]
    cases.append(f06)

    f07 = _case("F-07", "`library_delete_document` 生效", "MCP stdio", strategy_config_id)
    f07.status = f_payload["delete"]["status"]
    f07.evidence = f_payload["delete"]
    cases.append(f07)

    f08 = _case("F-08", "`library_query_assets` 返回资产", "MCP stdio", strategy_config_id)
    f08.status = f_payload["query_assets"]["status"]
    f08.evidence = f_payload["query_assets"]
    cases.append(f08)

    f09 = _case("F-09", "无效参数时 JSON-RPC 错误可读", "MCP stdio", strategy_config_id)
    f09.status = f_payload["invalid_params"]["status"]
    f09.evidence = f_payload["invalid_params"]
    cases.append(f09)

    f10 = _case("F-10", "查询返回图片相关多模态证据", "MCP stdio", strategy_config_id)
    f10.status = f_payload["multimodal_query"]["status"]
    f10.evidence = f_payload["multimodal_query"]
    cases.append(f10)

    f11 = _case("F-11", "Server 长会话查询稳定", "MCP stdio", strategy_config_id)
    f11.status = f_payload["session_stability"]["status"]
    f11.evidence = f_payload["session_stability"]
    cases.append(f11)

    f12 = _case("F-12", "引用透明性检查", "MCP stdio", strategy_config_id)
    f12.status = f_payload["citation_transparency"]["status"]
    f12.evidence = f_payload["citation_transparency"]
    cases.append(f12)

    # G. Profile 切换与对比
    compare_payload = run_compare(
        run_id=run_id,
        strategies=list(REAL_COMPARE_DEFAULTS),
        top_k=args.top_k,
    )

    g01 = _case("G-01", "固定 REAL profile 对比", "Profile 对比", strategy_config_id)
    g01.evidence = {
        "strategies": compare_payload.get("strategies"),
        "summary": compare_payload.get("summary"),
    }
    if compare_payload.get("summary", {}).get("fail", 0) > 0 or compare_payload.get(
        "summary", {}
    ).get("blocked", 0) > 0:
        g01.status = "FAIL"
        first_failure = compare_payload.get("first_failure") or {}
        failure = first_failure.get("failure") or {}
        g01.failure = build_failure(
            stage=str(failure.get("stage") or "compare"),
            location="compare_profiles.run_compare",
            provider_model=str(failure.get("provider_model") or "compare::profiles"),
            raw_error=str(failure.get("raw_error") or "profile_compare_failed"),
            fallback=str(failure.get("fallback") or "not_triggered"),
        )
    cases.append(g01)

    g02 = _case("G-02", "比较 ingest 结果一致性", "Profile 对比", strategy_config_id)
    compare_rows = compare_payload.get("results") or []
    ingest_matrix = {
        row.get("strategy_config_id"): {
            "embedder_provider_id": row.get("embedder_provider_id"),
            "embedder_model": row.get("embedder_model"),
            "ingest_success_count": row.get("ingest_success_count"),
            "ingests": row.get("ingests") or [],
        }
        for row in compare_rows
    }
    g02.evidence = {
        "ingest_matrix": ingest_matrix
    }
    success_counts = {row.get("ingest_success_count") for row in compare_rows}
    embedder_provider_ids = {row.get("embedder_provider_id") for row in compare_rows}
    per_file_counts: dict[str, set[tuple[int, int, int]]] = {}
    for row in compare_rows:
        for ingest in row.get("ingests") or []:
            file_name = str(ingest.get("file") or "")
            per_file_counts.setdefault(file_name, set()).add(
                (
                    int(ingest.get("chunks_written") or 0),
                    int(ingest.get("dense_written") or 0),
                    int(ingest.get("sparse_written") or 0),
                )
            )
    if (
        not all((row.get("ingest_success_count") or 0) >= 2 for row in compare_rows)
        or len(success_counts) != 1
        or len(embedder_provider_ids) != 1
        or any(len(counts) != 1 for counts in per_file_counts.values())
    ):
        g02.status = "FAIL"
        g02.failure = build_failure(
            stage="compare_ingest",
            location="compare_profiles.run_compare",
            provider_model="compare::profiles",
            raw_error="ingest_consistency_mismatch",
        )
    cases.append(g02)

    g03 = _case("G-03", "比较 query Top 命中差异", "Profile 对比", strategy_config_id)
    top_hit_matrix = {
        row.get("strategy_config_id"): {
            "query_top_doc_id": row.get("query_top_doc_id"),
            "query_top_chunk_id": row.get("query_top_chunk_id"),
            "query_top_section_path": row.get("query_top_section_path"),
            "query_top_score": row.get("query_top_score"),
            "query_top_source": row.get("query_top_source"),
        }
        for row in compare_rows
    }
    g03.evidence = {
        "top_hit_matrix": top_hit_matrix
    }
    if not all(
        row.get("query_top_doc_id")
        and row.get("query_top_chunk_id")
        and row.get("query_top_section_path")
        and isinstance(row.get("query_top_score"), (int, float))
        and row.get("query_top_source")
        for row in compare_rows
    ):
        g03.status = "FAIL"
        g03.failure = build_failure(
            stage="compare_query",
            location="compare_profiles.run_compare",
            provider_model="compare::profiles",
            raw_error="query_top_hit_matrix_incomplete",
        )
    cases.append(g03)

    g04 = _case("G-04", "比较 eval 指标差异", "Profile 对比", strategy_config_id)
    g04.evidence = {"metric_deltas": compare_payload.get("metric_deltas") or {}}
    if not isinstance(compare_payload.get("metric_deltas"), dict):
        g04.status = "FAIL"
        g04.failure = build_failure(
            stage="compare_eval",
            location="compare_profiles.run_compare",
            provider_model="compare::profiles",
            raw_error="metric_deltas_missing",
        )
    cases.append(g04)

    g05 = _case("G-05", "比较 rerank/fallback 差异", "Profile 对比", strategy_config_id)
    diff_summary = compare_payload.get("difference_summary") or []
    rerank_matrix = {
        row.get("strategy_config_id"): {
            "difference_sources": row.get("difference_sources") or [],
            "reranker_provider_id": row.get("reranker_provider_id"),
            "rerank_applied": row.get("rerank_applied"),
            "rerank_failed": row.get("rerank_failed"),
            "effective_rank_source": row.get("effective_rank_source"),
            "rerank_latency_ms": row.get("rerank_latency_ms"),
        }
        for row in diff_summary
    }
    g05.evidence = {"rerank_matrix": rerank_matrix}
    rerank_rows = [
        row
        for row in diff_summary
        if row.get("reranker_provider_id") not in {None, "", "noop", "reranker.noop"}
    ]
    if (
        not rerank_rows
        or not any(
            row.get("rerank_applied") is True
            and row.get("effective_rank_source") == "rerank"
            and isinstance(row.get("rerank_latency_ms"), (int, float))
            for row in rerank_rows
        )
        or not any(
            row.get("reranker_provider_id") in {None, "", "noop", "reranker.noop"}
            and row.get("difference_sources")
            and "baseline" in (row.get("difference_sources") or [])
            for row in diff_summary
        )
    ):
        g05.status = "FAIL"
        g05.failure = build_failure(
            stage="compare_rerank",
            location="compare_profiles.run_compare",
            provider_model="compare::profiles",
            raw_error="rerank_behavior_matrix_incomplete",
        )
    cases.append(g05)

    # 删除场景: E-08 + H-02..H-04
    simple_doc_id = evidence["doc_ids_by_alias"].get("simple")
    delete_result = None
    q_after_delete = None
    delete_dash = None
    if simple_doc_id:
        delete_result = admin_runner.delete_document(doc_id=simple_doc_id, mode="soft")
        q_after_delete = query_runner.run(
            "Sample Document PDF loader", strategy_config_id=strategy_config_id, top_k=args.top_k
        )
        evidence["deleted_doc_id"] = simple_doc_id
        evidence["trace_ids"].append(delete_result.trace_id)
        delete_dash = run_dashboard_checks(main_settings_path, evidence)

    e08 = _case("E-08", "include_deleted 一致性", "Dashboard API", strategy_config_id)
    e08.evidence = (delete_dash or {}).get("checks", {}).get("delete_consistency", {})
    if (delete_dash or {}).get("checks", {}).get("delete_consistency", {}).get("status") != "PASS":
        e08.status = "FAIL"
        e08.failure = build_failure(
            stage="dashboard_delete_consistency",
            location="check_dashboard_consistency.run_dashboard_checks",
            provider_model="dashboard::api",
            raw_error="include_deleted_mismatch",
        )
    cases.append(e08)

    e09 = _case("E-09", "文档分页参数生效", "Dashboard API", strategy_config_id)
    try:
        page1 = client.get("/api/documents?limit=2&offset=0").json().get("items") or []
        page2 = client.get("/api/documents?limit=2&offset=2").json().get("items") or []
        ids1 = {item.get("doc_id") for item in page1}
        ids2 = {item.get("doc_id") for item in page2}
        e09.evidence = {"page1_count": len(page1), "page2_count": len(page2)}
        if not page1 or not page2 or ids1.intersection(ids2):
            e09.status = "FAIL"
            e09.failure = build_failure(
                stage="dashboard_pagination",
                location="run_real_suite.main",
                provider_model="dashboard::api",
                raw_error="pagination_not_effective",
            )
    except Exception as exc:
        e09.status = "FAIL"
        e09.failure = _failure_from_exc(
            stage="dashboard_pagination",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            exc=exc,
        )
    cases.append(e09)

    e10 = _case("E-10", "trace 筛选参数生效", "Dashboard API", strategy_config_id)
    try:
        filtered = client.get(
            f"/api/traces?trace_type=query&status=ok&strategy_config_id={strategy_config_id}&limit=100&offset=0"
        ).json().get("items") or []
        e10.evidence = {
            "filtered_count": len(filtered),
            "sample_items": filtered[:3],
        }
        if not filtered or any(
            item.get("trace_type") != "query"
            or item.get("status") != "ok"
            or item.get("strategy_config_id") != strategy_config_id
            for item in filtered
        ):
            e10.status = "FAIL"
            e10.failure = build_failure(
                stage="dashboard_trace_filters",
                location="run_real_suite.main",
                provider_model="dashboard::api",
                raw_error="trace_filters_not_effective",
            )
    except Exception as exc:
        e10.status = "FAIL"
        e10.failure = _failure_from_exc(
            stage="dashboard_trace_filters",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            exc=exc,
        )
    cases.append(e10)

    # H. 数据生命周期
    h01 = _case("H-01", "重复摄取幂等", "CLI 摄取", strategy_config_id, status=b08.status)
    h01.evidence = dict(b08.evidence)
    h01.failure = b08.failure
    cases.append(h01)

    h02 = _case("H-02", "删除后查询不再命中", "删除 + 查询", strategy_config_id)
    h03 = _case("H-03", "删除后 dashboard 同步变化", "删除 + Dashboard API", strategy_config_id)
    h04 = _case(
        "H-04",
        "软删除后 `include_deleted` 可见",
        "删除 + Dashboard API",
        strategy_config_id,
    )
    deleted_hits = [
        src.doc_id
        for src in (q_after_delete.sources if q_after_delete else [])
        if src.doc_id == simple_doc_id
    ]
    h02.evidence = {
        "deleted_doc_id": simple_doc_id,
        "query_trace_id": q_after_delete.trace_id if q_after_delete else None,
        "query_deleted_hits": len(deleted_hits),
    }
    if deleted_hits:
        h02.status = "FAIL"
        h02.failure = build_failure(
            stage="delete_consistency",
            location="run_real_suite.main",
            provider_model="admin.delete::sqlite",
            raw_error="deleted_doc_still_queryable",
        )
    h03.evidence = (delete_dash or {}).get("checks", {}).get("delete_consistency", {})
    if (delete_dash or {}).get("checks", {}).get("delete_consistency", {}).get("visible_in_active"):
        h03.status = "FAIL"
        h03.failure = build_failure(
            stage="delete_consistency",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="deleted_doc_still_visible_in_active_browser",
        )
    h04.evidence = (delete_dash or {}).get("checks", {}).get("delete_consistency", {})
    if not (delete_dash or {}).get("checks", {}).get("delete_consistency", {}).get(
        "visible_in_include_deleted"
    ):
        h04.status = "FAIL"
        h04.failure = build_failure(
            stage="delete_consistency",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            raw_error="deleted_doc_missing_from_include_deleted",
        )
    cases.extend([h02, h03, h04])

    h05 = _case("H-05", "重新摄取已删除文档恢复可查", "摄取 + 查询 + Dashboard", strategy_config_id)
    try:
        reinjest = ingester.run(
            fixture_path("simple.pdf"), strategy_config_id=strategy_config_id, policy="new_version"
        )
        reinjest_structured = dict(reinjest.structured or {})
        q_after_reingest = query_runner.run(
            "Sample Document PDF loader", strategy_config_id=strategy_config_id, top_k=args.top_k
        )
        client_after_reingest = _dashboard_client(main_settings_path)
        active_doc_ids = {
            item.get("doc_id")
            for item in (
                client_after_reingest.get("/api/documents?limit=200&offset=0")
                .json()
                .get("items")
                or []
            )
        }
        h05.evidence = {
            "doc_id": reinjest_structured.get("doc_id"),
            "reingest_status": reinjest_structured.get("status"),
            "query_top_doc_id": (
                q_after_reingest.sources[0].doc_id if q_after_reingest.sources else None
            ),
            "active_doc_visible": reinjest_structured.get("doc_id") in active_doc_ids,
        }
        if not (
            reinjest_structured.get("status") == "ok"
            and reinjest_structured.get("doc_id") in active_doc_ids
            and any(
                src.doc_id == reinjest_structured.get("doc_id")
                for src in q_after_reingest.sources
            )
        ):
            h05.status = "FAIL"
            h05.failure = build_failure(
                stage="reingest_restore",
                location="run_real_suite.main",
                provider_model="ingest::pipeline",
                raw_error="reingest_restore_failed",
            )
    except Exception as exc:
        h05.status = "FAIL"
        h05.failure = _failure_from_exc(
            stage="reingest_restore",
            location="run_real_suite.main",
            provider_model="ingest::pipeline",
            exc=exc,
        )
    cases.append(h05)

    # I. 故障注入与恢复
    i01 = _case("I-01", "缺失 strategy 的报错链路", "故障注入", strategy_config_id)
    i01.status = a04.status
    i01.evidence = dict(missing_strategy_evidence)
    if missing_strategy_failure is not None:
        i01.failure = missing_strategy_failure
    cases.append(i01)

    i02 = _case("I-02", "embedder 网络失败诊断", "故障注入", broken_embedder_strategy_id)
    i02.status = c09.status
    i02.evidence = dict(c09.evidence)
    if broken_query_failure is not None:
        i02.failure = broken_query_failure
    cases.append(i02)

    broken_llm_strategy = strategy_path_for(run_id, "broken-llm")
    write_strategy_yaml(
        broken_llm_strategy,
        base_strategy_id="local.default",
        raw_override={
            "providers": {
                "llm": {
                    "provider_id": "openai_compatible",
                    "params": {
                        "model": "qwen-turbo",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "qa-plus-key",
                        "timeout_s": 1,
                    },
                }
            }
        },
    )
    i03 = _case("I-03", "llm 失败诊断", "故障注入", str(broken_llm_strategy))
    try:
        llm_settings = _make_settings(
            run_id=run_id,
            suffix="llm-failure",
            strategy_config_id=str(broken_llm_strategy),
        )
        llm_bundle = _runtime_bundle(llm_settings)
        llm_resp = llm_bundle["query_runner"].run(
            relevant_query, strategy_config_id=str(broken_llm_strategy), top_k=3
        )
        fallback_event = _find_trace_event(
            llm_resp.trace, span_name="generate", kind_contains="warn.generate_fallback"
        )
        i03.evidence = {
            "trace_id": llm_resp.trace_id,
            "fallback_event": fallback_event,
            "content_preview": llm_resp.content_md[:120],
        }
        if fallback_event is None or "extractive fallback" not in llm_resp.content_md:
            i03.status = "FAIL"
            i03.failure = build_failure(
                stage="generate",
                location="run_real_suite.main",
                provider_model="llm::openai_compatible::qwen-turbo",
                raw_error="generate_fallback_not_observed",
                fallback="expected_extract_fallback",
            )
    except Exception as exc:
        i03.status = "FAIL"
        i03.failure = _failure_from_exc(
            stage="generate",
            location="run_real_suite.main",
            provider_model="llm::openai_compatible::qwen-turbo",
            exc=exc,
            fallback="expected_extract_fallback",
        )
    cases.append(i03)

    broken_reranker_strategy = strategy_path_for(run_id, "broken-reranker")
    write_strategy_yaml(
        broken_reranker_strategy,
        base_strategy_id="local.production_like",
        raw_override={
            "providers": {
                "reranker": {
                    "provider_id": "openai_compatible_llm",
                    "params": {
                        "model": "qwen-turbo",
                        "base_url": "http://127.0.0.1:9/v1",
                        "api_key": "qa-plus-key",
                        "timeout_s": 1,
                        "max_candidates": 8,
                        "max_chunk_chars": 600,
                        "rerank_profile_id": "qa-plus.broken-reranker",
                    },
                }
            }
        },
    )
    i04 = _case("I-04", "reranker 失败诊断", "故障注入", str(broken_reranker_strategy))
    try:
        rerank_settings = _make_settings(
            run_id=run_id,
            suffix="rerank-failure",
            strategy_config_id=str(broken_reranker_strategy),
        )
        rerank_bundle = _runtime_bundle(rerank_settings)
        rerank_resp = rerank_bundle["query_runner"].run(
            relevant_query, strategy_config_id=str(broken_reranker_strategy), top_k=5
        )
        fallback_event = _find_trace_event(
            rerank_resp.trace, span_name="rerank", kind_contains="warn.rerank_fallback"
        )
        rerank_used = _find_trace_event(
            rerank_resp.trace, span_name="rerank", kind_contains="rerank.used"
        )
        i04.evidence = {
            "trace_id": rerank_resp.trace_id,
            "fallback_event": fallback_event,
            "rerank_used": rerank_used,
        }
        if fallback_event is None:
            i04.status = "FAIL"
            i04.failure = build_failure(
                stage="rerank",
                location="run_real_suite.main",
                provider_model="reranker::openai_compatible_llm::qwen-turbo",
                raw_error="rerank_fallback_not_observed",
                fallback="expected_fusion_retained",
            )
    except Exception as exc:
        i04.status = "FAIL"
        i04.failure = _failure_from_exc(
            stage="rerank",
            location="run_real_suite.main",
            provider_model="reranker::openai_compatible_llm::qwen-turbo",
            exc=exc,
            fallback="expected_fusion_retained",
        )
    cases.append(i04)

    i05 = _case("I-05", "dashboard API 读取空库", "Dashboard API", strategy_config_id)
    try:
        empty_settings = _make_settings(
            run_id=run_id,
            suffix="empty-dashboard",
            strategy_config_id="local.default",
        )
        empty_client = _dashboard_client(empty_settings)
        empty_overview = empty_client.get("/api/overview").json()
        empty_docs = empty_client.get("/api/documents?limit=20&offset=0").json()
        empty_traces = empty_client.get("/api/traces?limit=20&offset=0").json()
        empty_eval_runs = empty_client.get("/api/eval/runs?limit=20&offset=0").json()
        empty_trends = empty_client.get("/api/eval/trends?metric=hit_rate@k&window=30").json()
        i05.evidence = {
            "docs": (empty_overview.get("assets") or {}).get("docs"),
            "chunks": (empty_overview.get("assets") or {}).get("chunks"),
            "documents_count": len(empty_docs.get("items") or []),
            "traces_count": len(empty_traces.get("items") or []),
            "eval_runs_count": len(empty_eval_runs.get("items") or []),
            "trend_points": len(empty_trends.get("points") or []),
        }
        if not (
            i05.evidence["docs"] == 0
            and i05.evidence["chunks"] == 0
            and i05.evidence["documents_count"] == 0
            and i05.evidence["traces_count"] == 0
            and i05.evidence["eval_runs_count"] == 0
            and i05.evidence["trend_points"] == 0
        ):
            i05.status = "FAIL"
            i05.failure = build_failure(
                stage="dashboard_empty",
                location="run_real_suite.main",
                provider_model="dashboard::api",
                raw_error="empty_dashboard_not_clean",
            )
    except Exception as exc:
        i05.status = "FAIL"
        i05.failure = _failure_from_exc(
            stage="dashboard_empty",
            location="run_real_suite.main",
            provider_model="dashboard::api",
            exc=exc,
        )
    cases.append(i05)

    i06 = _case("I-06", "部分成功链路的回填格式正确", "Progress Writer", strategy_config_id)
    try:
        from write_progress import _render_run_block

        sample_payload = {
            "run_id": f"{run_id}_sample",
            "strategy_config_id": strategy_config_id,
            "settings_path": str(main_settings_path),
            "result_json": "data/sample.json",
            "summary": {"PASS": 1, "FAIL": 1, "BLOCKED": 1, "TOTAL": 3},
            "cases": [
                _case("X-01", "示例通过", "CLI", strategy_config_id).to_dict(),
                _expected_failure_case(
                    _case("X-02", "示例失败", "CLI", strategy_config_id),
                    status="FAIL",
                    evidence={"trace_id": "trace_x2"},
                    failure=build_failure(
                        stage="query",
                        location="demo",
                        provider_model="llm::demo",
                        raw_error="boom",
                    ),
                ).to_dict(),
                _expected_failure_case(
                    _case("X-03", "示例阻塞", "CLI", strategy_config_id),
                    status="BLOCKED(env:network)",
                    evidence={"trace_id": "trace_x3"},
                    failure=build_failure(
                        stage="preflight_dns",
                        location="demo",
                        provider_model="embedder::demo",
                        raw_error="dns failure",
                    ),
                ).to_dict(),
            ],
        }
        rendered = _render_run_block(sample_payload)
        i06.evidence = {
            "has_run_header": "### Run" in rendered,
            "has_table_header": (
                "| 用例ID | 标题 | 状态 | 执行入口 | 关键证据 | 失败链路 |" in rendered
            ),
            "has_failure_section": "**失败诊断**" in rendered,
        }
        if not all(i06.evidence.values()):
            i06.status = "FAIL"
            i06.failure = build_failure(
                stage="progress_render",
                location="run_real_suite.main",
                provider_model="progress::writer",
                raw_error="progress_render_missing_required_sections",
            )
    except Exception as exc:
        i06.status = "FAIL"
        i06.failure = _failure_from_exc(
            stage="progress_render",
            location="run_real_suite.main",
            provider_model="progress::writer",
            exc=exc,
        )
    cases.append(i06)

    i07 = _case("I-07", "settings 文件语法错误提示清晰", "配置解析", strategy_config_id)
    try:
        bad_settings_path = settings_path_for(run_id, suffix="broken-settings-syntax")
        bad_settings_path.parent.mkdir(parents=True, exist_ok=True)
        bad_settings_path.write_text(
            "paths:\n  data_dir data/broken\nserver:\n  dashboard_port: 7860\n",
            encoding="utf-8",
        )
        try:
            activate_runtime(bad_settings_path)
            i07.status = "FAIL"
            i07.failure = build_failure(
                stage="settings_parse",
                location="run_real_suite.main",
                provider_model="settings::loader",
                raw_error="expected_settings_parse_error",
            )
        except Exception as exc:
            i07.evidence = {
                "settings_path": str(bad_settings_path),
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            if ":" not in str(exc) and "yaml" not in str(exc).lower():
                i07.status = "FAIL"
                i07.failure = _failure_from_exc(
                    stage="settings_parse",
                    location="run_real_suite.main",
                    provider_model="settings::loader",
                    exc=exc,
                )
    except Exception as exc:
        i07.status = "FAIL"
        i07.failure = _failure_from_exc(
            stage="settings_parse",
            location="run_real_suite.main",
            provider_model="settings::loader",
            exc=exc,
        )
    cases.append(i07)

    i08 = _case("I-08", "strategy 缺少必填 provider 配置", "配置解析", strategy_config_id)
    try:
        broken_provider_strategy = strategy_path_for(run_id, "missing-embedder-provider-id")
        write_strategy_yaml(
            broken_provider_strategy,
            base_strategy_id="local.default",
            raw_override={"providers": {"embedder": {"params": {"model": "text-embedding-v3"}}}},
        )
        try:
            query_runner.run(
                "Sample Document PDF loader",
                strategy_config_id=str(broken_provider_strategy),
                top_k=3,
            )
            i08.status = "FAIL"
            i08.failure = build_failure(
                stage="strategy_validation",
                location="run_real_suite.main",
                provider_model="strategy::embedder",
                raw_error="expected_missing_provider_id_error",
            )
        except Exception as exc:
            i08.evidence = {
                "strategy_path": str(broken_provider_strategy),
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            if "provider_id" not in str(exc):
                i08.status = "FAIL"
                i08.failure = _failure_from_exc(
                    stage="strategy_validation",
                    location="run_real_suite.main",
                    provider_model="strategy::embedder",
                    exc=exc,
                )
    except Exception as exc:
        i08.status = "FAIL"
        i08.failure = _failure_from_exc(
            stage="strategy_validation",
            location="run_real_suite.main",
            provider_model="strategy::embedder",
            exc=exc,
        )
    cases.append(i08)

    i09 = _case(
        "I-09",
        "traces.jsonl 被删除后的 Dashboard 空态",
        "Dashboard API",
        strategy_config_id,
    )
    try:
        deleted_trace_settings = _make_settings(
            run_id=run_id,
            suffix="deleted-trace-file",
            strategy_config_id="local.default",
        )
        deleted_bundle = _runtime_bundle(deleted_trace_settings)
        deleted_ingest = deleted_bundle["ingester"].run(
            fixture_path("simple.pdf"), strategy_config_id="local.default", policy="new_version"
        )
        deleted_bundle["query_runner"].run(
            "Sample Document PDF loader", strategy_config_id="local.default", top_k=3
        )
        deleted_logs = deleted_bundle["settings"].paths.logs_dir / "traces.jsonl"
        if deleted_logs.exists():
            deleted_logs.unlink()
        deleted_client = _dashboard_client(deleted_trace_settings)
        deleted_overview = deleted_client.get("/api/overview").json()
        deleted_traces = deleted_client.get("/api/traces?limit=20&offset=0").json()
        i09.evidence = {
            "doc_id": (deleted_ingest.structured or {}).get("doc_id"),
            "overview_docs": int((deleted_overview.get("assets") or {}).get("docs") or 0),
            "providers": deleted_overview.get("providers") or {},
            "trace_count": len(deleted_traces.get("items") or []),
            "trace_file_exists": deleted_logs.exists(),
        }
        if not (
            i09.evidence["overview_docs"] > 0
            and i09.evidence["trace_count"] == 0
            and i09.evidence["providers"] == {}
            and i09.evidence["trace_file_exists"] is False
        ):
            i09.status = "FAIL"
            i09.failure = build_failure(
                stage="dashboard_deleted_trace_file",
                location="run_real_suite.main",
                provider_model="dashboard::jsonl_reader",
                raw_error="dashboard_should_show_empty_trace_state_after_trace_file_deleted",
            )
    except Exception as exc:
        i09.status = "FAIL"
        i09.failure = _failure_from_exc(
            stage="dashboard_deleted_trace_file",
            location="run_real_suite.main",
            provider_model="dashboard::jsonl_reader",
            exc=exc,
        )
    cases.append(i09)

    i10 = _case("I-10", "traces.jsonl 含损坏行时跳过坏行", "Dashboard API", strategy_config_id)
    try:
        corrupt_trace_settings = _make_settings(
            run_id=run_id,
            suffix="corrupt-trace-file",
            strategy_config_id="local.default",
        )
        corrupt_bundle = _runtime_bundle(corrupt_trace_settings)
        corrupt_query = corrupt_bundle["query_runner"].run(
            "Sample Document PDF loader", strategy_config_id="local.default", top_k=3
        )
        corrupt_logs = corrupt_bundle["settings"].paths.logs_dir / "traces.jsonl"
        with corrupt_logs.open("a", encoding="utf-8") as f:
            f.write("broken line\n")
            f.write("{\"trace_id\":\"missing_fields\"}\n")
        corrupt_client = _dashboard_client(corrupt_trace_settings)
        corrupt_overview = corrupt_client.get("/api/overview")
        corrupt_traces = corrupt_client.get("/api/traces?limit=20&offset=0")
        corrupt_overview.raise_for_status()
        corrupt_traces.raise_for_status()
        trace_items = corrupt_traces.json().get("items") or []
        trace_ids = [item.get("trace_id") for item in trace_items]
        i10.evidence = {
            "expected_trace_id": corrupt_query.trace_id,
            "trace_ids": trace_ids[:10],
            "trace_count": len(trace_items),
            "providers_present": bool(corrupt_overview.json().get("providers")),
        }
        if not (
            corrupt_query.trace_id in trace_ids
            and len(trace_items) >= 1
            and i10.evidence["providers_present"] is True
        ):
            i10.status = "FAIL"
            i10.failure = build_failure(
                stage="dashboard_corrupt_trace_file",
                location="run_real_suite.main",
                provider_model="dashboard::jsonl_reader",
                raw_error="dashboard_failed_to_skip_corrupt_trace_lines",
            )
    except Exception as exc:
        i10.status = "FAIL"
        i10.failure = _failure_from_exc(
            stage="dashboard_corrupt_trace_file",
            location="run_real_suite.main",
            provider_model="dashboard::jsonl_reader",
            exc=exc,
        )
    cases.append(i10)

    i11 = _case("I-11", "调小 chunk_size 后分块数增多", "摄取参数变更", strategy_config_id)
    try:
        chunk_default_settings = _make_settings(
            run_id=run_id,
            suffix="chunk-default",
            strategy_config_id="local.default",
        )
        chunk_small_strategy = strategy_path_for(run_id, "chunk-size-300")
        write_strategy_yaml(
            chunk_small_strategy,
            base_strategy_id="local.default",
            raw_override={"providers": {"chunker": {"params": {"chunk_size": 300}}}},
        )
        chunk_small_settings = _make_settings(
            run_id=run_id,
            suffix="chunk-size-300",
            strategy_config_id=str(chunk_small_strategy),
        )
        default_bundle = _runtime_bundle(chunk_default_settings)
        small_bundle = _runtime_bundle(chunk_small_settings)
        default_resp = default_bundle["ingester"].run(
            fixture_path("complex_technical_doc.pdf"),
            strategy_config_id="local.default",
            policy="new_version",
        )
        small_resp = small_bundle["ingester"].run(
            fixture_path("complex_technical_doc.pdf"),
            strategy_config_id=str(chunk_small_strategy),
            policy="new_version",
        )
        default_chunks = int(
            ((default_resp.structured or {}).get("counts") or {}).get("chunks_written", 0)
        )
        small_chunks = int(
            ((small_resp.structured or {}).get("counts") or {}).get("chunks_written", 0)
        )
        i11.evidence = {
            "file": "complex_technical_doc.pdf",
            "default_chunk_size": 800,
            "adjusted_chunk_size": 300,
            "default_chunks_written": default_chunks,
            "adjusted_chunks_written": small_chunks,
        }
        if not (default_chunks > 0 and small_chunks > default_chunks):
            i11.status = "FAIL"
            i11.failure = build_failure(
                stage="chunk_size_adjustment",
                location="run_real_suite.main",
                provider_model="chunker::rcts_within_section",
                raw_error="smaller_chunk_size_should_increase_chunk_count",
            )
    except Exception as exc:
        i11.status = "FAIL"
        i11.failure = _failure_from_exc(
            stage="chunk_size_adjustment",
            location="run_real_suite.main",
            provider_model="chunker::rcts_within_section",
            exc=exc,
        )
    cases.append(i11)

    i12 = _case("I-12", "chunk_overlap=0 时相邻块重叠减少", "摄取参数变更", strategy_config_id)
    try:
        overlap_default_settings = _make_settings(
            run_id=run_id,
            suffix="overlap-default",
            strategy_config_id="local.default",
        )
        overlap_zero_strategy = strategy_path_for(run_id, "chunk-overlap-zero")
        write_strategy_yaml(
            overlap_zero_strategy,
            base_strategy_id="local.default",
            raw_override={"providers": {"chunker": {"params": {"chunk_overlap": 0}}}},
        )
        overlap_zero_settings = _make_settings(
            run_id=run_id,
            suffix="overlap-zero",
            strategy_config_id=str(overlap_zero_strategy),
        )
        overlap_default_bundle = _runtime_bundle(overlap_default_settings)
        overlap_zero_bundle = _runtime_bundle(overlap_zero_settings)
        overlap_default_resp = overlap_default_bundle["ingester"].run(
            fixture_path("complex_technical_doc.pdf"),
            strategy_config_id="local.default",
            policy="new_version",
        )
        overlap_zero_resp = overlap_zero_bundle["ingester"].run(
            fixture_path("complex_technical_doc.pdf"),
            strategy_config_id=str(overlap_zero_strategy),
            policy="new_version",
        )
        default_chunk_ids = overlap_default_bundle["sqlite"].fetch_chunk_ids(
            doc_id=str((overlap_default_resp.structured or {}).get("doc_id") or ""),
            version_id=str((overlap_default_resp.structured or {}).get("version_id") or ""),
        )
        zero_chunk_ids = overlap_zero_bundle["sqlite"].fetch_chunk_ids(
            doc_id=str((overlap_zero_resp.structured or {}).get("doc_id") or ""),
            version_id=str((overlap_zero_resp.structured or {}).get("version_id") or ""),
        )
        default_chunks = sorted(
            overlap_default_bundle["sqlite"].fetch_chunks(default_chunk_ids),
            key=lambda item: item.chunk_index,
        )
        zero_chunks = sorted(
            overlap_zero_bundle["sqlite"].fetch_chunks(zero_chunk_ids),
            key=lambda item: item.chunk_index,
        )
        if len(default_chunks) < 2 or len(zero_chunks) < 2:
            raise RuntimeError("not_enough_chunks_for_overlap_check")
        default_overlap = _longest_suffix_prefix_overlap(
            default_chunks[0].chunk_text, default_chunks[1].chunk_text
        )
        zero_overlap = _longest_suffix_prefix_overlap(
            zero_chunks[0].chunk_text, zero_chunks[1].chunk_text
        )
        i12.evidence = {
            "file": "complex_technical_doc.pdf",
            "default_chunk_overlap": 120,
            "adjusted_chunk_overlap": 0,
            "default_observed_overlap_chars": default_overlap,
            "adjusted_observed_overlap_chars": zero_overlap,
        }
        if not (zero_overlap <= default_overlap and zero_overlap <= 5):
            i12.status = "FAIL"
            i12.failure = build_failure(
                stage="chunk_overlap_adjustment",
                location="run_real_suite.main",
                provider_model="chunker::rcts_within_section",
                raw_error="chunk_overlap_zero_should_reduce_adjacent_text_overlap",
            )
    except Exception as exc:
        i12.status = "FAIL"
        i12.failure = _failure_from_exc(
            stage="chunk_overlap_adjustment",
            location="run_real_suite.main",
            provider_model="chunker::rcts_within_section",
            exc=exc,
        )
    cases.append(i12)

    # J. LLM 切换 — DeepSeek
    deepseek_strategy_id = "local.production_like_deepseek"
    deepseek_query = "Retrieval-Augmented Generation modular architecture"
    deepseek_settings_path = _make_settings(
        run_id=run_id,
        suffix="deepseek-main",
        strategy_config_id=deepseek_strategy_id,
    )

    j01 = _case("J-01", "DeepSeek LLM strategy 可装配", "Provider 预检", deepseek_strategy_id)
    deepseek_preflight_status, deepseek_preflight_evidence, deepseek_preflight_failure = (
        preflight_real(deepseek_settings_path, deepseek_strategy_id)
    )
    deepseek_checks = {
        str(item.get("kind") or ""): item
        for item in (deepseek_preflight_evidence.get("checks") or [])
        if isinstance(item, dict)
    }
    llm_check = deepseek_checks.get("llm") or {}
    embedder_check = deepseek_checks.get("embedder") or {}
    j01.evidence = {
        "preflight_status": deepseek_preflight_status,
        "llm_check": llm_check,
        "embedder_check": embedder_check,
        "reranker_check": deepseek_checks.get("reranker") or {},
    }
    reranker_check = deepseek_checks.get("reranker") or {}
    if (
        deepseek_preflight_status == "PASS"
        and llm_check.get("host") == "api.deepseek.com"
        and llm_check.get("model") == "deepseek-chat"
        and embedder_check.get("host") == "dashscope.aliyuncs.com"
        and embedder_check.get("model") == "text-embedding-v3"
        and reranker_check.get("host") == "api.deepseek.com"
        and reranker_check.get("model") == "deepseek-chat"
    ):
        j01.status = "PASS"
    else:
        j01.status = "FAIL"
        if deepseek_preflight_failure is not None:
            j01.failure = deepseek_preflight_failure
        else:
            j01.failure = build_failure(
                stage="deepseek_preflight",
                location="run_real_suite.main",
                provider_model="llm::openai_compatible::deepseek-chat",
                raw_error="deepseek_preflight_checks_incomplete",
            )
    cases.append(j01)

    deepseek_bundle: dict[str, Any] | None = None
    deepseek_complex_doc_id = ""
    deepseek_simple_doc_id = ""
    deepseek_endpoints: dict[str, Any] = {}
    if j01.status == "PASS":
        try:
            deepseek_bundle = _runtime_bundle(deepseek_settings_path)
            deepseek_settings = deepseek_bundle["settings"]
            deepseek_endpoints = deepseek_settings.raw.get("model_endpoints") or {}
            deepseek_complex = deepseek_bundle["ingester"].run(
                fixture_path("complex_technical_doc.pdf"),
                strategy_config_id=deepseek_strategy_id,
                policy="new_version",
            )
            deepseek_simple = deepseek_bundle["ingester"].run(
                fixture_path("simple.pdf"),
                strategy_config_id=deepseek_strategy_id,
                policy="new_version",
            )
            deepseek_complex_doc_id = str(
                (deepseek_complex.structured or {}).get("doc_id") or ""
            )
            deepseek_simple_doc_id = str(
                (deepseek_simple.structured or {}).get("doc_id") or ""
            )
        except Exception:
            deepseek_bundle = None

    j02 = _case("J-02", "DeepSeek LLM — CLI 查询", "CLI 查询", deepseek_strategy_id)
    try:
        deepseek_cli = _run_query_cli(
            query=deepseek_query,
            strategy_config_id=deepseek_strategy_id,
            top_k=5,
            settings_path=deepseek_settings_path,
            verbose=True,
        )
        deepseek_verbose = deepseek_cli.get("verbose") or {}
        deepseek_sources = deepseek_verbose.get("sources") or []
        deepseek_llm = (deepseek_verbose.get("providers") or {}).get("llm") or {}
        j02.evidence = {
            "query": deepseek_query,
            "trace_id": deepseek_cli.get("trace_id"),
            "source_count": len(deepseek_sources),
            "llm_provider": deepseek_llm,
            "top_source": deepseek_sources[0] if deepseek_sources else {},
        }
        if not (
            deepseek_cli.get("trace_id")
            and deepseek_sources
            and any(src.get("doc_id") == deepseek_complex_doc_id for src in deepseek_sources)
            and deepseek_llm.get("provider_id") == "openai_compatible"
            and deepseek_llm.get("model") == "deepseek-chat"
            and "api.deepseek.com" in str(deepseek_llm.get("base_url") or "")
        ):
            j02.status = "FAIL"
            j02.failure = build_failure(
                stage="deepseek_query",
                location="run_real_suite.main",
                provider_model="llm::openai_compatible::deepseek-chat",
                raw_error="deepseek_cli_query_validation_failed",
            )
    except Exception as exc:
        j02.status = "FAIL"
        j02.failure = _failure_from_exc(
            stage="deepseek_query",
            location="run_real_suite.main",
            provider_model="llm::openai_compatible::deepseek-chat",
            exc=exc,
        )
    cases.append(j02)

    j03 = _case(
        "J-03",
        "DeepSeek LLM — Dashboard Overview 反映配置",
        "CLI 查询 + Dashboard API",
        deepseek_strategy_id,
    )
    try:
        deepseek_client = _dashboard_client(deepseek_settings_path)
        overview = deepseek_client.get("/api/overview").json()
        overview_llm = (overview.get("providers") or {}).get("llm") or {}
        j03.evidence = {
            "overview_llm": overview_llm,
            "assets": overview.get("assets") or {},
        }
        if not (
            overview_llm.get("provider_id") == "openai_compatible"
            and overview_llm.get("model") == "deepseek-chat"
            and "api.deepseek.com" in str(overview_llm.get("base_url") or "")
        ):
            j03.status = "FAIL"
            j03.failure = build_failure(
                stage="dashboard_overview",
                location="run_real_suite.main",
                provider_model="dashboard::overview::llm",
                raw_error="dashboard_overview_missing_deepseek_llm",
            )
    except Exception as exc:
        j03.status = "FAIL"
        j03.failure = _failure_from_exc(
            stage="dashboard_overview",
            location="run_real_suite.main",
            provider_model="dashboard::overview::llm",
            exc=exc,
        )
    cases.append(j03)

    j04 = _case("J-04", "DeepSeek 与 Qwen LLM 查询结果对比", "Profile 对比", deepseek_strategy_id)
    try:
        llm_compare = run_compare(
            run_id=run_id,
            strategies=["local.production_like", deepseek_strategy_id],
            top_k=args.top_k,
        )
        compare_rows = llm_compare.get("results") or []
        llm_matrix = {
            row.get("strategy_config_id"): {
                "llm_provider_id": row.get("llm_provider_id"),
                "llm_model": row.get("llm_model"),
                "llm_base_url": row.get("llm_base_url"),
                "reranker_provider_id": row.get("reranker_provider_id"),
                "reranker_model": row.get("reranker_model"),
                "reranker_base_url": row.get("reranker_base_url"),
                "query_top_doc_id": row.get("query_top_doc_id"),
                "query_top_chunk_id": row.get("query_top_chunk_id"),
                "query_top_section_path": row.get("query_top_section_path"),
            }
            for row in compare_rows
        }
        qwen_row = llm_matrix.get("local.production_like") or {}
        deepseek_row = llm_matrix.get(deepseek_strategy_id) or {}
        j04.evidence = {
            "strategies": llm_compare.get("strategies") or [],
            "llm_matrix": llm_matrix,
        }
        if not (
            set(llm_matrix) == {"local.production_like", deepseek_strategy_id}
            and qwen_row.get("llm_model") == "qwen-turbo"
            and "dashscope.aliyuncs.com" in str(qwen_row.get("llm_base_url") or "")
            and deepseek_row.get("llm_model") == "deepseek-chat"
            and "api.deepseek.com" in str(deepseek_row.get("llm_base_url") or "")
            and qwen_row.get("reranker_model") == "qwen-turbo"
            and "dashscope.aliyuncs.com" in str(qwen_row.get("reranker_base_url") or "")
            and deepseek_row.get("reranker_model") == "deepseek-chat"
            and "api.deepseek.com" in str(deepseek_row.get("reranker_base_url") or "")
            and qwen_row.get("query_top_chunk_id")
            and deepseek_row.get("query_top_chunk_id")
        ):
            j04.status = "FAIL"
            j04.failure = build_failure(
                stage="compare_query_llm_switch",
                location="compare_profiles.run_compare",
                provider_model="compare::qwen_vs_deepseek",
                raw_error="deepseek_compare_matrix_incomplete",
            )
    except Exception as exc:
        j04.status = "FAIL"
        j04.failure = _failure_from_exc(
            stage="compare_query_llm_switch",
            location="compare_profiles.run_compare",
            provider_model="compare::qwen_vs_deepseek",
            exc=exc,
        )
    cases.append(j04)

    j05 = _case("J-05", "DeepSeek API Key 无效时报错清晰", "查询链路", deepseek_strategy_id)
    try:
        bad_key_settings = _make_settings(
            run_id=run_id,
            suffix="deepseek-bad-key",
            strategy_config_id=deepseek_strategy_id,
            providers_override={
                "llm": {
                    "params": {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": "sk-invalid-deepseek-key",
                    }
                }
            },
        )
        bad_key_bundle = _runtime_bundle(bad_key_settings)
        bad_key_bundle["ingester"].run(
            Path(__file__).resolve().parents[3] / "DEV_SPEC.md",
            strategy_config_id=deepseek_strategy_id,
            policy="new_version",
        )
        bad_key_resp = bad_key_bundle["query_runner"].run(
            deepseek_query, strategy_config_id=deepseek_strategy_id, top_k=5
        )
        fallback_event = _find_trace_event(
            bad_key_resp.trace, span_name="generate", kind_contains="warn.generate_fallback"
        )
        bad_key_trace = _dashboard_client(bad_key_settings).get(
            f"/api/trace/{bad_key_resp.trace_id}"
        ).json()
        error_events = bad_key_trace.get("error_events") or []
        error_text = json.dumps(error_events[:2], ensure_ascii=False)
        auth_like = any(
            token in error_text.lower()
            for token in (
                "401",
                "unauthorized",
                "authentication",
                "invalid api key",
                "incorrect api key",
            )
        )
        j05.evidence = {
            "trace_id": bad_key_resp.trace_id,
            "fallback_event": fallback_event,
            "error_events": error_events[:2],
            "content_preview": bad_key_resp.content_md[:120],
        }
        if not (
            fallback_event is not None
            and error_events
            and (auth_like or any(event.get("kind") == "llm.http_error" for event in error_events))
        ):
            j05.status = "FAIL"
            j05.failure = build_failure(
                stage="deepseek_auth",
                location="run_real_suite.main",
                provider_model="llm::openai_compatible::deepseek-chat",
                raw_error="deepseek_invalid_api_key_not_surfaceable",
                fallback="expected_extract_fallback",
            )
    except Exception as exc:
        j05.status = "FAIL"
        j05.failure = _failure_from_exc(
            stage="deepseek_auth",
            location="run_real_suite.main",
            provider_model="llm::openai_compatible::deepseek-chat",
            exc=exc,
            fallback="expected_extract_fallback",
        )
    cases.append(j05)

    j06 = _case(
        "J-06",
        "Qwen Embedding + DeepSeek LLM 混合链路",
        "摄取 + 查询",
        deepseek_strategy_id,
    )
    try:
        if deepseek_bundle is None:
            raise RuntimeError("deepseek_bundle_not_ready")
        mixed_resp = deepseek_bundle["query_runner"].run(
            "Sample Document PDF loader", strategy_config_id=deepseek_strategy_id, top_k=3
        )
        mixed_providers = (mixed_resp.trace.providers or {}) if mixed_resp.trace is not None else {}
        embedder_meta = mixed_providers.get("embedder") or {}
        llm_meta = mixed_providers.get("llm") or {}
        reranker_meta = mixed_providers.get("reranker") or {}
        j06.evidence = {
            "trace_id": mixed_resp.trace_id,
            "embedder": embedder_meta,
            "llm": llm_meta,
            "reranker": reranker_meta,
            "top_source": (
                mixed_resp.sources[0].to_dict()
                if mixed_resp.sources and hasattr(mixed_resp.sources[0], "to_dict")
                else {}
            ),
        }
        if not (
            mixed_resp.sources
            and any(src.doc_id == deepseek_simple_doc_id for src in mixed_resp.sources)
            and embedder_meta.get("model") == "text-embedding-v3"
            and "dashscope.aliyuncs.com" in str(embedder_meta.get("base_url") or "")
            and llm_meta.get("model") == "deepseek-chat"
            and "api.deepseek.com" in str(llm_meta.get("base_url") or "")
            and reranker_meta.get("model") == "deepseek-chat"
            and "api.deepseek.com" in str(reranker_meta.get("base_url") or "")
        ):
            j06.status = "FAIL"
            j06.failure = build_failure(
                stage="deepseek_mixed_chain",
                location="run_real_suite.main",
                provider_model="embedder::qwen + llm/reranker::deepseek",
                raw_error="mixed_chain_snapshot_incomplete_or_query_missed_simple_pdf",
            )
    except Exception as exc:
        j06.status = "FAIL"
        j06.failure = _failure_from_exc(
            stage="deepseek_mixed_chain",
            location="run_real_suite.main",
            provider_model="embedder::qwen + llm/reranker::deepseek",
            exc=exc,
        )
    cases.append(j06)

    j07 = _case("J-07", "Ragas / Judge 使用 DeepSeek", "CLI 评估", deepseek_strategy_id)
    try:
        qwen_endpoint = deepseek_endpoints.get("qwen") or {}
        deepseek_eval_settings = _make_settings(
            run_id=run_id,
            suffix="deepseek-eval",
            strategy_config_id=deepseek_strategy_id,
            providers_override={
                "judge": {
                    "provider_id": "openai_compatible",
                    "params": {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": str(
                            (deepseek_endpoints.get("deepseek") or {}).get("api_key") or ""
                        ),
                        "model": "deepseek-chat",
                        "timeout_s": 30,
                    },
                },
                "evaluator": {
                    "provider_id": "ragas",
                    "params": {
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key": str(
                            (deepseek_endpoints.get("deepseek") or {}).get("api_key") or ""
                        ),
                        "model": "deepseek-chat",
                        "embedding_model": "text-embedding-v3",
                        "embedding_base_url": str(qwen_endpoint.get("base_url") or ""),
                        "embedding_api_key": str(qwen_endpoint.get("api_key") or ""),
                    },
                },
            },
        )
        deepseek_eval_bundle = _runtime_bundle(deepseek_eval_settings)
        deepseek_eval_bundle["ingester"].run(
            Path(__file__).resolve().parents[3] / "DEV_SPEC.md",
            strategy_config_id=deepseek_strategy_id,
            policy="new_version",
        )
        deepseek_eval_cli = _run_eval_cli(
            dataset_id="rag_eval_small",
            strategy_config_id=deepseek_strategy_id,
            top_k=3,
            settings_path=deepseek_eval_settings,
            verbose=True,
        )
        eval_verbose = deepseek_eval_cli.get("verbose") or {}
        eval_metrics = eval_verbose.get("metrics") or {}
        eval_cases = eval_verbose.get("cases") or []
        first_case = eval_cases[0] if eval_cases else {}
        first_artifacts = first_case.get("artifacts") or {}
        artifacts_text = json.dumps(first_artifacts, ensure_ascii=False)
        j07.evidence = {
            "run_id": eval_verbose.get("run_id"),
            "metrics": eval_metrics,
            "first_case": {
                "case_id": first_case.get("case_id"),
                "trace_id": first_case.get("trace_id"),
                "artifacts": first_artifacts,
            },
        }
        if not (
            eval_verbose.get("run_id")
            and eval_cases
            and (
                any(key.startswith("ragas.") for key in eval_metrics.keys())
                or (
                    first_artifacts.get("error") == "backend_error"
                    and "deepseek-chat" in artifacts_text
                    and "api.deepseek.com" in artifacts_text
                )
            )
        ):
            j07.status = "FAIL"
            j07.failure = build_failure(
                stage="deepseek_eval",
                location="run_real_suite.main",
                provider_model="evaluator::ragas::deepseek-chat",
                raw_error="deepseek_eval_missing_metrics_or_provider_error_artifacts",
            )
    except Exception as exc:
        j07.status = "FAIL"
        j07.failure = _failure_from_exc(
            stage="deepseek_eval",
            location="run_real_suite.main",
            provider_model="evaluator::ragas::deepseek-chat",
            exc=exc,
        )
    cases.append(j07)

    # N. 数据生命周期闭环
    n01 = _case("N-01", "完整闭环：摄取→查询→软删除→查询", "数据生命周期", strategy_config_id)
    try:
        n01_settings = _make_settings(
            run_id=run_id,
            suffix="n01-lifecycle",
            strategy_config_id=strategy_config_id,
        )
        n01_bundle = _runtime_bundle(n01_settings)
        n01_ingest = n01_bundle["ingester"].run(
            fixture_path("simple.pdf"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        n01_doc_id = str((n01_ingest.structured or {}).get("doc_id") or "")
        n01_before = n01_bundle["query_runner"].run(
            "Sample Document PDF loader", strategy_config_id=strategy_config_id, top_k=3
        )
        n01_delete = n01_bundle["admin_runner"].delete_document(doc_id=n01_doc_id, mode="soft")
        n01_after = n01_bundle["query_runner"].run(
            "Sample Document PDF loader", strategy_config_id=strategy_config_id, top_k=3
        )
        hits_before = [src.doc_id for src in n01_before.sources if src.doc_id == n01_doc_id]
        hits_after = [src.doc_id for src in n01_after.sources if src.doc_id == n01_doc_id]
        n01.evidence = {
            "doc_id": n01_doc_id,
            "ingest_trace_id": n01_ingest.trace_id,
            "query_before_trace_id": n01_before.trace_id,
            "delete_trace_id": n01_delete.trace_id,
            "query_after_trace_id": n01_after.trace_id,
            "hits_before_delete": len(hits_before),
            "hits_after_delete": len(hits_after),
        }
        if not (n01_doc_id and hits_before and not hits_after):
            n01.status = "FAIL"
            n01.failure = build_failure(
                stage="lifecycle_soft_delete",
                location="run_real_suite.main",
                provider_model="admin.delete::soft",
                raw_error="soft_delete_closed_loop_failed",
            )
    except Exception as exc:
        n01.status = "FAIL"
        n01.failure = _failure_from_exc(
            stage="lifecycle_soft_delete",
            location="run_real_suite.main",
            provider_model="admin.delete::soft",
            exc=exc,
        )
    cases.append(n01)

    n02 = _case("N-02", "硬删除清理底层存储", "数据生命周期", strategy_config_id)
    try:
        n02_settings = _make_settings(
            run_id=run_id,
            suffix="n02-hard-delete",
            strategy_config_id=strategy_config_id,
        )
        n02_bundle = _runtime_bundle(n02_settings)
        n02_ingest = n02_bundle["ingester"].run(
            fixture_path("with_images.pdf"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        n02_structured = dict(n02_ingest.structured or {})
        n02_doc_id = str(n02_structured.get("doc_id") or "")
        n02_version_id = str(n02_structured.get("version_id") or "")
        n02_hashes = n02_bundle["sqlite"].fetch_doc_version_hashes(
            doc_id=n02_doc_id, version_id=n02_version_id
        )
        n02_delete = n02_bundle["admin_runner"].delete_document(doc_id=n02_doc_id, mode="hard")
        remaining_chunks = n02_bundle["sqlite"].fetch_chunk_ids(doc_id=n02_doc_id)
        remaining_assets = n02_bundle["sqlite"].fetch_asset_ids_by_doc_version(doc_id=n02_doc_id)
        remaining_hashes = n02_bundle["sqlite"].fetch_doc_version_hashes(doc_id=n02_doc_id)
        md_dir = n02_bundle["settings"].paths.md_dir / n02_doc_id
        raw_exists = any(
            (n02_bundle["settings"].paths.raw_dir / f"{file_hash}.pdf").exists()
            for file_hash in n02_hashes
        )
        n02.evidence = {
            "doc_id": n02_doc_id,
            "version_id": n02_version_id,
            "delete_trace_id": n02_delete.trace_id,
            "delete_status": n02_delete.status,
            "affected": n02_delete.affected,
            "remaining_chunks": len(remaining_chunks),
            "remaining_assets": len(remaining_assets),
            "remaining_hashes": len(remaining_hashes),
            "md_dir_exists": md_dir.exists(),
            "raw_exists": raw_exists,
        }
        if not (
            n02_delete.status == "ok"
            and len(remaining_chunks) == 0
            and len(remaining_assets) == 0
            and len(remaining_hashes) == 0
            and md_dir.exists() is False
            and raw_exists is False
        ):
            n02.status = "FAIL"
            n02.failure = build_failure(
                stage="lifecycle_hard_delete",
                location="run_real_suite.main",
                provider_model="admin.delete::hard",
                raw_error="hard_delete_storage_cleanup_incomplete",
            )
    except Exception as exc:
        n02.status = "FAIL"
        n02.failure = _failure_from_exc(
            stage="lifecycle_hard_delete",
            location="run_real_suite.main",
            provider_model="admin.delete::hard",
            exc=exc,
        )
    cases.append(n02)

    n03 = _case("N-03", "删除一个文档不影响另一文档查询", "数据生命周期", strategy_config_id)
    try:
        n03_settings = _make_settings(
            run_id=run_id,
            suffix="n03-multi-doc",
            strategy_config_id=strategy_config_id,
        )
        n03_bundle = _runtime_bundle(n03_settings)
        n03_simple = n03_bundle["ingester"].run(
            fixture_path("simple.pdf"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        n03_complex = n03_bundle["ingester"].run(
            fixture_path("complex_technical_doc.pdf"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        n03_simple_doc_id = str((n03_simple.structured or {}).get("doc_id") or "")
        n03_complex_doc_id = str((n03_complex.structured or {}).get("doc_id") or "")
        n03_bundle["admin_runner"].delete_document(doc_id=n03_simple_doc_id, mode="soft")
        n03_query = n03_bundle["query_runner"].run(
            "Retrieval-Augmented Generation modular architecture",
            strategy_config_id=strategy_config_id,
            top_k=3,
        )
        complex_hits = [src.doc_id for src in n03_query.sources if src.doc_id == n03_complex_doc_id]
        deleted_hits = [src.doc_id for src in n03_query.sources if src.doc_id == n03_simple_doc_id]
        n03.evidence = {
            "deleted_doc_id": n03_simple_doc_id,
            "surviving_doc_id": n03_complex_doc_id,
            "query_trace_id": n03_query.trace_id,
            "complex_hits": len(complex_hits),
            "deleted_hits": len(deleted_hits),
        }
        if not (complex_hits and not deleted_hits):
            n03.status = "FAIL"
            n03.failure = build_failure(
                stage="lifecycle_doc_isolation",
                location="run_real_suite.main",
                provider_model="admin.delete::soft",
                raw_error="deleting_one_doc_should_not_break_other_doc_recall",
            )
    except Exception as exc:
        n03.status = "FAIL"
        n03.failure = _failure_from_exc(
            stage="lifecycle_doc_isolation",
            location="run_real_suite.main",
            provider_model="admin.delete::soft",
            exc=exc,
        )
    cases.append(n03)

    n04 = _case("N-04", "硬删除后重新摄取恢复可查", "数据生命周期", strategy_config_id)
    try:
        n04_settings = _make_settings(
            run_id=run_id,
            suffix="n04-hard-delete-restore",
            strategy_config_id=strategy_config_id,
        )
        n04_bundle = _runtime_bundle(n04_settings)
        n04_first = n04_bundle["ingester"].run(
            fixture_path("simple.pdf"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        n04_first_doc_id = str((n04_first.structured or {}).get("doc_id") or "")
        n04_bundle["admin_runner"].delete_document(doc_id=n04_first_doc_id, mode="hard")
        n04_second = n04_bundle["ingester"].run(
            fixture_path("simple.pdf"),
            strategy_config_id=strategy_config_id,
            policy="new_version",
        )
        n04_second_doc_id = str((n04_second.structured or {}).get("doc_id") or "")
        n04_query = n04_bundle["query_runner"].run(
            "Sample Document PDF loader", strategy_config_id=strategy_config_id, top_k=3
        )
        n04_hits = [src.doc_id for src in n04_query.sources if src.doc_id == n04_second_doc_id]
        n04.evidence = {
            "first_doc_id": n04_first_doc_id,
            "second_doc_id": n04_second_doc_id,
            "query_trace_id": n04_query.trace_id,
            "restored_hits": len(n04_hits),
        }
        if not (n04_second_doc_id and n04_hits):
            n04.status = "FAIL"
            n04.failure = build_failure(
                stage="lifecycle_hard_delete_restore",
                location="run_real_suite.main",
                provider_model="admin.delete::hard",
                raw_error="hard_delete_reingest_restore_failed",
            )
    except Exception as exc:
        n04.status = "FAIL"
        n04.failure = _failure_from_exc(
            stage="lifecycle_hard_delete_restore",
            location="run_real_suite.main",
            provider_model="admin.delete::hard",
            exc=exc,
        )
    cases.append(n04)

    # O. 文档替换与多场景验证
    o_cases = [
        (
            "O-01",
            "中文技术文档命中",
            "chinese_technical_doc.pdf",
            "Modular RAG 设计理念",
            ["Modular RAG", "可独立替换", "模块"],
        ),
        (
            "O-02",
            "中文表格文档命中",
            "chinese_table_chart_doc.pdf",
            "BGE-large-zh Cross-Encoder",
            ["BGE-large-zh", "Cross-Encoder"],
        ),
        (
            "O-03",
            "中文流程图文档命中",
            "chinese_table_chart_doc.pdf",
            "RAG 数据摄取流程图",
            ["流程图", "RAG", "数据摄取"],
        ),
        (
            "O-04",
            "中文长文档前半章节命中",
            "chinese_long_doc.pdf",
            "RoPE 位置编码",
            ["RoPE", "位置编码"],
        ),
        (
            "O-05",
            "中文长文档后半章节命中",
            "chinese_long_doc.pdf",
            "项目实战经验总结",
            ["项目实战", "经验总结"],
        ),
        (
            "O-06",
            "英文技术文档命中",
            "complex_technical_doc.pdf",
            "ChromaDB text-embedding-ada-002 vector storage",
            ["ChromaDB", "text-embedding-ada-002"],
        ),
    ]
    for case_id, title, file_name, query_text, keywords in o_cases:
        ocase = _case(case_id, title, "样本文档验证", strategy_config_id)
        try:
            recall = _run_single_doc_recall_case(
                run_id=run_id,
                suffix=f"sample-{case_id.lower()}",
                strategy_config_id=strategy_config_id,
                file_name=file_name,
                query=query_text,
                top_k=3,
                required_keywords=keywords,
            )
            ocase.evidence = {
                "file": file_name,
                "query": query_text,
                "doc_id": recall.get("doc_id"),
                "query_trace_id": recall.get("query_trace_id"),
                "top_doc_id": recall.get("top_doc_id"),
                "top_chunk_id": recall.get("top_chunk_id"),
                "top_section_path": recall.get("top_section_path"),
                "matched_keywords": recall.get("matched_keywords"),
                "text_hits": recall.get("text_hits"),
            }
            if not (
                recall.get("doc_id")
                and recall.get("source_count", 0) > 0
                and recall.get("top_doc_id") == recall.get("doc_id")
                and len(recall.get("matched_keywords") or []) >= 1
            ):
                ocase.status = "FAIL"
                ocase.failure = build_failure(
                    stage="sample_doc_recall",
                    location="run_real_suite.main",
                    provider_model=f"query::{file_name}",
                    raw_error="sample_document_query_failed_to_hit_expected_doc",
                )
        except Exception as exc:
            ocase.status = "FAIL"
            ocase.failure = _failure_from_exc(
                stage="sample_doc_recall",
                location="run_real_suite.main",
                provider_model=f"query::{file_name}",
                exc=exc,
            )
        cases.append(ocase)

    summary = summary_counts(cases)
    result_json = Path("data") / "qa_plus_runs" / run_id / "results" / "suite_results.json"
    payload = {
        "run_id": run_id,
        "strategy_config_id": strategy_config_id,
        "settings_path": str(main_settings_path),
        "result_json": str(result_json),
        "cases": [case.to_dict() for case in cases],
        "summary": summary,
        "compare": compare_payload,
    }
    json_dump(result_json, payload)

    if write_progress_enabled:
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "write_progress.py"),
                "--result-json",
                str(result_json),
            ],
            check=True,
        )

    print(result_json)
    return 0 if summary["FAIL"] == 0 and summary["BLOCKED"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
