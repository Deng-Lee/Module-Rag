from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core.strategy.models import Settings
from src.observability.dashboard.app import create_app
from src.observability.obs import api as obs
from src.observability.sinks.jsonl import JsonlSink
from src.observability.trace.context import TraceContext
from src.ingestion.stages.storage.sqlite import SqliteStore


@pytest.mark.e2e
def test_dashboard_api_smoke(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"

    settings = Settings.from_dict(
        {
            "paths": {
                "data_dir": str(data_dir),
                "raw_dir": str(data_dir / "raw"),
                "md_dir": str(data_dir / "md"),
                "assets_dir": str(data_dir / "assets"),
                "chroma_dir": str(data_dir / "chroma"),
                "sqlite_dir": str(data_dir / "sqlite"),
                "cache_dir": str(tmp_path / "cache"),
                "logs_dir": str(logs_dir),
            },
            "server": {"dashboard_host": "127.0.0.1", "dashboard_port": 7860},
            "defaults": {"strategy_config_id": "local.default"},
        }
    )

    # Prepare a trace in JSONL (reader fallback path).
    sink = JsonlSink(logs_dir)
    ctx = TraceContext.new("trace_dash", trace_type="query", strategy_config_id="local.default")
    with TraceContext.activate(ctx):
        with obs.with_stage("query_norm"):
            obs.event("query.normalized", {"query_hash": "h", "rewrite_used": False})
        ctx.replay_keys["query_hash"] = "h"
        env = ctx.finish()
    sink.on_trace_end(env)

    # Prepare sqlite doc/chunk data for /api/documents and /api/chunk
    sqlite = SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")
    sqlite.upsert_doc_version_minimal("doc_1", "ver_1", file_sha256="h", status="indexed")
    sqlite.upsert_chunk(
        chunk_id="chk_1",
        doc_id="doc_1",
        version_id="ver_1",
        section_id="sec_1",
        section_path="Intro",
        chunk_index=1,
        chunk_text="hello",
    )
    sqlite.upsert_chunk_asset(chunk_id="chk_1", asset_id="asset_1")

    app = create_app(settings)
    client = TestClient(app)

    r = client.get("/api/overview")
    assert r.status_code == 200
    body = r.json()
    assert "assets" in body and "health" in body

    r = client.get("/api/traces?limit=5")
    assert r.status_code == 200
    assert "items" in r.json()

    r = client.get("/api/trace/trace_dash")
    assert r.status_code == 200
    assert r.json().get("trace_id") == "trace_dash"

    r = client.get("/api/documents?limit=5")
    assert r.status_code == 200
    assert r.json().get("items")

    r = client.get("/api/chunk/chk_1")
    assert r.status_code == 200
    assert r.json().get("chunk_id") == "chk_1"

    # Negative payloads should return structured errors without crashing.
    r = client.post("/api/ingest", json={})
    assert r.status_code == 200
    assert r.json().get("status") == "error"

    r = client.post("/api/delete", json={})
    assert r.status_code == 200
    assert r.json().get("status") == "error"

    r = client.get("/api/eval/runs")
    assert r.status_code == 200
    assert "items" in r.json()
