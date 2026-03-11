# ruff: noqa: E402, I001
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from qa_plus_common import activate_runtime, json_load


def run_dashboard_checks(settings_path: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    settings = activate_runtime(settings_path)

    from fastapi.testclient import TestClient

    from src.observability.dashboard.app import create_app

    app = create_app(settings)
    client = TestClient(app)

    results: dict[str, Any] = {}

    overview = client.get("/api/overview")
    overview.raise_for_status()
    overview_body = overview.json()
    expected_docs = len(evidence.get("doc_ids_active") or [])
    results["overview"] = {
        "docs": int((overview_body.get("assets") or {}).get("docs") or 0),
        "chunks": int((overview_body.get("assets") or {}).get("chunks") or 0),
        "providers_present": bool(overview_body.get("providers")),
        "status": "PASS"
        if int((overview_body.get("assets") or {}).get("docs") or 0) >= expected_docs
        else "FAIL",
    }

    docs_resp = client.get("/api/documents?limit=100&offset=0")
    docs_resp.raise_for_status()
    doc_items = docs_resp.json().get("items") or []
    doc_ids = {item.get("doc_id") for item in doc_items}
    active_expected = set(evidence.get("doc_ids_active") or [])
    results["browser"] = {
        "active_doc_ids": sorted([str(v) for v in doc_ids if v]),
        "expected_doc_ids": sorted(active_expected),
        "status": "PASS" if active_expected.issubset(doc_ids) else "FAIL",
    }

    sample_chunk_id = evidence.get("sample_chunk_id")
    if sample_chunk_id:
        chunk_resp = client.get(f"/api/chunk/{sample_chunk_id}")
        chunk_resp.raise_for_status()
        chunk_body = chunk_resp.json()
        results["chunk"] = {
            "chunk_id": chunk_body.get("chunk_id"),
            "asset_count": len(chunk_body.get("asset_ids") or []),
            "text_len": len(str(chunk_body.get("chunk_text") or "")),
            "status": "PASS" if chunk_body.get("chunk_id") == sample_chunk_id else "FAIL",
        }

    traces_resp = client.get("/api/traces?limit=200&offset=0")
    traces_resp.raise_for_status()
    trace_items = traces_resp.json().get("items") or []
    trace_ids = {item.get("trace_id") for item in trace_items}
    expected_trace_ids = set(evidence.get("trace_ids") or [])
    results["traces"] = {
        "expected_trace_ids": sorted([str(v) for v in expected_trace_ids if v]),
        "visible_trace_ids": sorted([str(v) for v in trace_ids if v])[:20],
        "status": "PASS" if expected_trace_ids.issubset(trace_ids) else "FAIL",
    }

    detail_ids = [tid for tid in (evidence.get("trace_ids") or []) if tid]
    detail_ok = True
    detail_rows: list[dict[str, Any]] = []
    for trace_id in detail_ids[:3]:
        detail_resp = client.get(f"/api/trace/{trace_id}")
        detail_resp.raise_for_status()
        detail_body = detail_resp.json()
        trace = detail_body.get("trace") or {}
        row = {
            "trace_id": trace_id,
            "returned_trace_id": trace.get("trace_id"),
            "error_events": len(detail_body.get("error_events") or []),
        }
        detail_rows.append(row)
        if trace.get("trace_id") != trace_id:
            detail_ok = False
    results["trace_detail"] = {
        "items": detail_rows,
        "status": "PASS" if detail_ok else "FAIL",
    }

    eval_run_id = evidence.get("eval_run_id")
    eval_runs_resp = client.get("/api/eval/runs?limit=50&offset=0")
    eval_runs_resp.raise_for_status()
    eval_items = eval_runs_resp.json().get("items") or []
    eval_run_ids = {item.get("run_id") for item in eval_items}
    trends_resp = client.get("/api/eval/trends?metric=hit_rate@k&window=30")
    trends_resp.raise_for_status()
    trend_points = len((trends_resp.json() or {}).get("points") or [])
    results["eval"] = {
        "run_id": eval_run_id,
        "run_visible": eval_run_id in eval_run_ids if eval_run_id else False,
        "trend_points": trend_points,
        "status": "PASS" if (eval_run_id in eval_run_ids and trend_points >= 1) else "FAIL",
    }

    deleted_doc_id = evidence.get("deleted_doc_id")
    if deleted_doc_id:
        inc_deleted = client.get("/api/documents?limit=100&offset=0&include_deleted=true")
        inc_deleted.raise_for_status()
        inc_items = inc_deleted.json().get("items") or []
        inc_doc_ids = {item.get("doc_id"): item.get("status") for item in inc_items}
        active_doc_ids = {item.get("doc_id") for item in doc_items}
        results["delete_consistency"] = {
            "deleted_doc_id": deleted_doc_id,
            "visible_in_active": deleted_doc_id in active_doc_ids,
            "visible_in_include_deleted": deleted_doc_id in inc_doc_ids,
            "deleted_status": inc_doc_ids.get(deleted_doc_id),
            "status": "PASS"
            if deleted_doc_id not in active_doc_ids and inc_doc_ids.get(deleted_doc_id) == "deleted"
            else "FAIL",
        }

    failing = [name for name, value in results.items() if value.get("status") == "FAIL"]
    return {
        "status": "PASS" if not failing else "FAIL",
        "checks": results,
        "failing_checks": failing,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--settings-path", required=True)
    p.add_argument("--evidence-json", required=True)
    args = p.parse_args()

    payload = run_dashboard_checks(Path(args.settings_path), json_load(Path(args.evidence_json)))
    print(payload)
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
