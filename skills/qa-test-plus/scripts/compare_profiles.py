# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from qa_plus_common import (
    REAL_COMPARE_DEFAULTS,
    activate_runtime,
    fixture_path,
    json_dump,
    merged_provider_specs,
    now_run_id,
    preflight_real,
    provider_model_label,
    wrap_runner,
    safe_metric_dict,
    settings_path_for,
    slugify,
    traces_have_event,
    write_real_settings,
)
from check_dashboard_consistency import run_dashboard_checks


def _difference_sources(row: dict[str, Any]) -> list[str]:
    sources: list[str] = []
    if row.get("reranker_provider_id") not in {None, "", "noop", "reranker.noop"}:
        sources.append("rerank")
    if row.get("nan_metrics"):
        sources.append("evaluator")
    if row.get("dashboard_status") != "PASS":
        sources.append("dashboard")
    if row.get("query_top_doc_id") is None:
        sources.append("retrieval")
    return sources or ["baseline"]


def run_compare(
    *,
    run_id: str,
    strategies: list[str],
    top_k: int,
) -> dict[str, Any]:
    from src.core.runners.eval import EvalRunner
    from src.core.runners.ingest import IngestRunner
    from src.core.runners.query import QueryRunner

    comparisons: list[dict[str, Any]] = []
    first_failure: dict[str, Any] | None = None

    for strategy_config_id in strategies:
        suffix = f"compare-{slugify(strategy_config_id)}"
        settings_path = settings_path_for(run_id, suffix=suffix)
        write_real_settings(
            settings_path, run_id=run_id, suffix=suffix, strategy_config_id=strategy_config_id
        )

        preflight_status, preflight_evidence, preflight_failure = preflight_real(
            settings_path, strategy_config_id
        )
        row: dict[str, Any] = {
            "strategy_config_id": strategy_config_id,
            "settings_path": str(settings_path),
            "status": preflight_status,
            "preflight": preflight_evidence,
        }
        if preflight_failure is not None:
            row["failure"] = {
                "stage": preflight_failure.stage,
                "location": preflight_failure.location,
                "provider_model": preflight_failure.provider_model,
                "raw_error": preflight_failure.raw_error,
                "fallback": preflight_failure.fallback,
            }
            if first_failure is None:
                first_failure = row
            comparisons.append(row)
            continue

        settings = activate_runtime(settings_path)
        merged_providers = merged_provider_specs(settings, strategy_config_id)
        ingester = wrap_runner(
            IngestRunner(settings_path=settings_path),
            operation=f"compare.ingester.run::{strategy_config_id}",
        )
        query_runner = wrap_runner(
            QueryRunner(settings_path=settings_path, settings=settings),
            operation=f"compare.query_runner.run::{strategy_config_id}",
        )
        evaluator = wrap_runner(
            EvalRunner(settings_path=settings_path, settings=settings),
            operation=f"compare.eval_runner.run::{strategy_config_id}",
        )
        embedder_spec = merged_providers.get("embedder") or {}
        llm_spec = merged_providers.get("llm") or {}

        ingest_rows: list[dict[str, Any]] = []
        for filename in ("simple.pdf", "complex_technical_doc.pdf"):
            resp = ingester.run(
                fixture_path(filename), strategy_config_id=strategy_config_id, policy="new_version"
            )
            structured = dict(resp.structured or {})
            if structured.get("status") not in {"ok", "skipped"}:
                row["status"] = "FAIL"
                row["failure"] = {
                    "stage": "ingest",
                    "location": "compare_profiles.run_compare",
                    "provider_model": "embedder/ingest::n/a",
                    "raw_error": str(structured.get("error") or "ingest_failed"),
                    "fallback": "not_triggered",
                }
                if first_failure is None:
                    first_failure = row
                break
            ingest_rows.append(
                {
                    "file": filename,
                    "trace_id": resp.trace_id,
                    "status": structured.get("status"),
                    "doc_id": structured.get("doc_id"),
                    "chunks_written": (structured.get("counts") or {}).get("chunks_written", 0),
                    "dense_written": (structured.get("counts") or {}).get("dense_written", 0),
                    "sparse_written": (structured.get("counts") or {}).get("sparse_written", 0),
                }
            )
        if row["status"] != "PASS":
            comparisons.append(row)
            continue

        qresp = query_runner.run(
            "Transformer 注意力机制是什么",
            strategy_config_id=strategy_config_id,
            top_k=top_k,
        )
        if not qresp.sources:
            row["status"] = "FAIL"
            row["failure"] = {
                "stage": "query",
                "location": "compare_profiles.run_compare",
                "provider_model": "query::n/a",
                "raw_error": "query_empty_sources",
                "fallback": "not_triggered",
            }
            if first_failure is None:
                first_failure = row
            comparisons.append(row)
            continue

        eval_result = evaluator.run(
            "rag_eval_small", strategy_config_id=strategy_config_id, top_k=top_k
        )
        metrics, nan_keys = safe_metric_dict(eval_result.metrics)

        evidence = {
            "doc_ids_active": [item["doc_id"] for item in ingest_rows if item.get("doc_id")],
            "trace_ids": [item["trace_id"] for item in ingest_rows if item.get("trace_id")]
            + [qresp.trace_id],
            "sample_chunk_id": qresp.sources[0].chunk_id,
            "eval_run_id": eval_result.run_id,
        }
        dash = run_dashboard_checks(settings_path, evidence)

        reranker = (
            ((qresp.trace.providers or {}).get("reranker") or {}) if qresp.trace is not None else {}
        )
        query_aggregates = (qresp.trace.aggregates or {}) if qresp.trace is not None else {}
        top_source = qresp.sources[0]
        row.update(
            {
                "status": "PASS" if not nan_keys and dash["status"] == "PASS" else "FAIL",
                "ingest_success_count": len(ingest_rows),
                "query_trace_id": qresp.trace_id,
                "query_top_chunk_id": top_source.chunk_id,
                "query_top_doc_id": top_source.doc_id,
                "query_top_section_path": top_source.section_path,
                "query_top_score": top_source.score,
                "query_top_source": top_source.source,
                "eval_run_id": eval_result.run_id,
                "metrics": metrics,
                "nan_metrics": nan_keys,
                "embedder_provider_id": embedder_spec.get("provider_id"),
                "embedder_model": ((embedder_spec.get("params") or {}).get("model")),
                "llm_provider_id": llm_spec.get("provider_id"),
                "llm_model": ((llm_spec.get("params") or {}).get("model")),
                "llm_base_url": ((llm_spec.get("params") or {}).get("base_url")),
                "reranker_provider_id": reranker.get("provider_id"),
                "reranker_model": reranker.get("model"),
                "reranker_base_url": reranker.get("base_url"),
                "rerank_applied": traces_have_event(qresp.trace, "rerank", "rerank.ranked"),
                "rerank_failed": query_aggregates.get("rerank_failed"),
                "effective_rank_source": query_aggregates.get("effective_rank_source"),
                "rerank_latency_ms": query_aggregates.get("rerank_latency_ms"),
                "dashboard_status": dash["status"],
                "dashboard_failing_checks": dash["failing_checks"],
                "ingests": ingest_rows,
            }
        )
        row["difference_sources"] = _difference_sources(row)
        if row["status"] != "PASS":
            row["failure"] = {
                "stage": "compare_validation",
                "location": "compare_profiles.run_compare",
                "provider_model": provider_model_label(
                    reranker.get("provider_id"), reranker.get("params")
                ),
                "raw_error": "compare_validation_failed",
                "fallback": "not_triggered",
            }
            if first_failure is None:
                first_failure = row
        comparisons.append(row)

    pass_rows = [item for item in comparisons if item.get("status") == "PASS"]
    metric_keys = sorted({key for row in pass_rows for key in (row.get("metrics") or {}).keys()})
    deltas: dict[str, float] = {}
    if len(pass_rows) >= 2:
        left = pass_rows[0].get("metrics") or {}
        right = pass_rows[1].get("metrics") or {}
        for key in metric_keys:
            lv = left.get(key)
            rv = right.get(key)
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                deltas[key] = float(rv) - float(lv)

    difference_summary: list[dict[str, Any]] = []
    for row in comparisons:
        difference_summary.append(
            {
                "strategy_config_id": row.get("strategy_config_id"),
                "difference_sources": row.get("difference_sources") or ["baseline"],
                "embedder_provider_id": row.get("embedder_provider_id"),
                "llm_provider_id": row.get("llm_provider_id"),
                "llm_model": row.get("llm_model"),
                "llm_base_url": row.get("llm_base_url"),
                "query_top_doc_id": row.get("query_top_doc_id"),
                "query_top_chunk_id": row.get("query_top_chunk_id"),
                "query_top_section_path": row.get("query_top_section_path"),
                "query_top_score": row.get("query_top_score"),
                "query_top_source": row.get("query_top_source"),
                "reranker_provider_id": row.get("reranker_provider_id"),
                "reranker_model": row.get("reranker_model"),
                "reranker_base_url": row.get("reranker_base_url"),
                "rerank_applied": row.get("rerank_applied"),
                "rerank_failed": row.get("rerank_failed"),
                "effective_rank_source": row.get("effective_rank_source"),
                "rerank_latency_ms": row.get("rerank_latency_ms"),
                "dashboard_status": row.get("dashboard_status"),
            }
        )

    summary = {
        "run_id": run_id,
        "strategies": strategies,
        "results": comparisons,
        "first_failure": first_failure,
        "metric_deltas": deltas,
        "difference_summary": difference_summary,
        "summary": {
            "total": len(comparisons),
            "pass": len([row for row in comparisons if row.get("status") == "PASS"]),
            "fail": len([row for row in comparisons if str(row.get("status")).startswith("FAIL")]),
            "blocked": len(
                [row for row in comparisons if str(row.get("status")).startswith("BLOCKED")]
            ),
        },
    }
    return summary


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=now_run_id())
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--strategies", nargs="*", default=list(REAL_COMPARE_DEFAULTS))
    args = p.parse_args()

    payload = run_compare(run_id=args.run_id, strategies=list(args.strategies), top_k=args.top_k)
    out_path = Path("data") / "qa_plus_runs" / args.run_id / "compare" / "compare_results.json"
    json_dump(out_path, payload)
    print(out_path)
    return 0 if payload["summary"]["fail"] == 0 and payload["summary"]["blocked"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
