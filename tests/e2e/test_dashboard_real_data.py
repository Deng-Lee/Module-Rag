from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core.runners.eval import EvalRunner
from src.core.runners.ingest import IngestRunner
from src.core.runners.query import QueryRunner
from src.core.strategy import load_settings
from src.observability.dashboard.app import create_app
from src.observability.obs import api as obs
from src.observability.sinks.jsonl import JsonlSink


def _write_settings_yaml(p: Path, *, data_dir: Path, logs_dir: Path) -> None:
    raw = "\n".join(
        [
            "paths:",
            f"  data_dir: {data_dir.as_posix()}",
            f"  raw_dir: {(data_dir / 'raw').as_posix()}",
            f"  md_dir: {(data_dir / 'md').as_posix()}",
            f"  assets_dir: {(data_dir / 'assets').as_posix()}",
            f"  chroma_dir: {(data_dir / 'chroma').as_posix()}",
            f"  sqlite_dir: {(data_dir / 'sqlite').as_posix()}",
            "  cache_dir: cache",
            f"  logs_dir: {logs_dir.as_posix()}",
            "",
            "defaults:",
            "  strategy_config_id: local.test",
            "",
            "eval:",
            "  datasets_dir: tests/datasets",
            "",
        ]
    )
    p.write_text(raw, encoding="utf-8")


def _load_retrieval_docs(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return list(raw.get("docs") or [])


@pytest.mark.e2e
def test_dashboard_with_real_data(tmp_path: Path, tmp_workdir: Path) -> None:
    _ = tmp_workdir

    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    settings_path = tmp_path / "settings.yaml"
    _write_settings_yaml(settings_path, data_dir=data_dir, logs_dir=logs_dir)

    # Ingest docs
    ds_path = Path(__file__).resolve().parents[1] / "datasets" / "retrieval_small.yaml"
    docs = _load_retrieval_docs(ds_path)
    ingester = IngestRunner(settings_path=settings_path)
    for doc in docs:
        md_path = tmp_path / f"{doc['name']}.md"
        md_path.write_text(doc["md"], encoding="utf-8")
        resp = ingester.run(md_path, strategy_config_id="local.test", policy="new_version")
        assert resp.structured.get("status") in {"ok", "skipped"}

    # Query trace -> JSONL
    obs.set_sink(JsonlSink(logs_dir))
    runner = QueryRunner(settings_path=settings_path)
    resp = runner.run("FTS5 BM25 inverted index", strategy_config_id="local.test", top_k=5)
    assert resp.trace_id

    # Eval run -> SQLite eval_runs
    evaluator = EvalRunner(settings_path=settings_path)
    eval_result = evaluator.run("rag_eval_small", strategy_config_id="local.test", top_k=5)
    assert eval_result.run_id

    settings = load_settings(settings_path)
    app = create_app(settings)
    client = TestClient(app)

    # Overview
    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["assets"]["docs"] >= 1

    # Traces list + detail
    r = client.get("/api/traces?limit=5")
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items
    trace_id = items[0]["trace_id"]

    r = client.get(f"/api/trace/{trace_id}")
    assert r.status_code == 200
    assert r.json().get("trace_id") == trace_id

    # Documents
    r = client.get("/api/documents?limit=5")
    assert r.status_code == 200
    assert r.json().get("items")

    # Eval runs
    r = client.get("/api/eval/runs?limit=5")
    assert r.status_code == 200
    assert r.json().get("items")
