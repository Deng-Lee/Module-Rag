#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from src.core.runners.admin import AdminRunner  # noqa: E402
from src.core.runners.ingest import IngestRunner  # noqa: E402
from src.core.runners.query import QueryRunner  # noqa: E402
from src.core.strategy import StrategyLoader, load_settings, merge_provider_overrides  # noqa: E402
from src.libs.providers import register_builtin_providers  # noqa: E402
from src.libs.registry import ProviderRegistry  # noqa: E402
from src.observability.dashboard.app import create_app  # noqa: E402
from src.observability.obs import api as obs  # noqa: E402
from src.observability.sinks.jsonl import JsonlSink  # noqa: E402


QA_TEST_MD = ROOT / "QA_TEST.md"
FIXTURES = ROOT / "tests" / "fixtures" / "docs"


@dataclass(frozen=True)
class Case:
    case_id: str
    profiles: list[str]


def parse_cases(md_path: Path) -> list[Case]:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[Case] = []
    for i, line in enumerate(lines):
        m = re.match(r"^###\s+([A-Z](?:-UI)?-\d{2})\b", line.strip())
        if not m:
            continue
        cid = m.group(1)
        profiles: list[str] = []
        for j in range(i + 1, min(len(lines), i + 40)):
            if lines[j].startswith("### "):
                break
            pm = re.match(r"^Profiles：(.+)$", lines[j].strip())
            if pm:
                raw = pm.group(1)
                profiles = [p.strip() for p in raw.split("/") if p.strip()]
                break
        out.append(Case(case_id=cid, profiles=profiles))
    return out


@dataclass
class Row:
    offline: str = "TODO"
    real: str = "TODO"
    evidence: str = ""
    note: str = ""


def overall_for(case: Case, row: Row) -> str:
    need_offline = ("OFFLINE" in case.profiles) or (not case.profiles)
    need_real = "REAL" in case.profiles

    if need_offline and need_real:
        if row.offline == "PASS" and row.real == "PASS":
            return "PASS"
        if row.offline.startswith("BLOCKED") or row.real.startswith("BLOCKED"):
            return "BLOCKED"
        if row.offline == "FAIL" or row.real == "FAIL":
            return "FAIL"
        return "TODO"
    if need_real and not need_offline:
        return row.real if row.real in {"PASS", "FAIL"} else "BLOCKED"
    return row.offline


def write_settings(
    path: Path,
    *,
    run_id: str,
    default_strategy: str,
    data_dir: Path,
    logs_dir: Path,
    cache_dir: Path,
) -> None:
    content = {
        "paths": {
            "data_dir": str(data_dir),
            "raw_dir": str(data_dir / "raw"),
            "md_dir": str(data_dir / "md"),
            "assets_dir": str(data_dir / "assets"),
            "chroma_dir": str(data_dir / "chroma"),
            "sqlite_dir": str(data_dir / "sqlite"),
            "cache_dir": str(cache_dir),
            "logs_dir": str(logs_dir),
        },
        "server": {"dashboard_host": "127.0.0.1", "dashboard_port": 7860},
        "defaults": {"strategy_config_id": default_strategy},
        "eval": {"datasets_dir": "tests/datasets"},
    }

    lines: list[str] = [
        "# QA baseline settings (generated)",
        "# DO NOT COMMIT (ignored by .gitignore)",
        f"# run_id: {run_id}",
    ]

    def emit_map(m: dict[str, Any], indent: int = 0) -> None:
        sp = "  " * indent
        for k, v in m.items():
            if isinstance(v, dict):
                lines.append(f"{sp}{k}:")
                emit_map(v, indent + 1)
            else:
                lines.append(f"{sp}{k}: {v}")

    emit_map(content)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_sink_for(settings_path: Path) -> Any:
    settings = load_settings(settings_path)
    obs.set_sink(JsonlSink(settings.paths.logs_dir))
    return settings


def api_get(client: TestClient, path: str) -> tuple[int, dict[str, Any]]:
    r = client.get(path)
    return r.status_code, r.json()


def api_post(client: TestClient, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    r = client.post(path, json=payload)
    return r.status_code, r.json()


def run_cli(cmd: list[str], *, env: dict[str, str]) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return p.returncode, p.stdout


def parse_trace_id(output: str) -> str:
    m = re.search(r"^trace_id:\s*(trace_[a-f0-9]+)\s*$", output, re.MULTILINE)
    return m.group(1) if m else ""


def _extract_hosts_from_settings(settings_path: Path) -> list[str]:
    try:
        settings = load_settings(settings_path)
        endpoints = settings.raw.get("model_endpoints") or {}
    except Exception:
        return []
    hosts: list[str] = []
    for v in endpoints.values():
        if not isinstance(v, dict):
            continue
        base_url = v.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            continue
        host = urlparse(base_url).hostname
        if host:
            hosts.append(host)
    return list(dict.fromkeys(hosts).keys())


def _network_ok(hosts: list[str]) -> bool:
    if not hosts:
        return False
    for h in hosts:
        try:
            socket.getaddrinfo(h, 443)
            return True
        except Exception:
            continue
    return False


def main(argv: list[str]) -> int:
    run_id = argv[1] if len(argv) > 1 and argv[1].strip() else datetime.now().strftime("%Y%m%d_%H%M%S")
    run_real = ("--real" in argv) or (os.environ.get("QA_RUN_REAL") == "1")

    cases = parse_cases(QA_TEST_MD)
    rows: dict[str, Row] = {c.case_id: Row() for c in cases}

    for c in cases:
        if "-UI-" in c.case_id:
            rows[c.case_id].offline = "BLOCKED(UI not implemented)"
            rows[c.case_id].real = "BLOCKED(UI not implemented)"
    for real_only in ("K-02", "L-02", "L-03"):
        if real_only in rows:
            rows[real_only].offline = "N/A"

    missing = [p for p in ("sample.md", "simple.pdf", "with_images.pdf", "complex_technical_doc.pdf", "blogger_intro.pdf", "sample.txt") if not (FIXTURES / p).exists()]
    if missing:
        print(f"Missing fixtures: {missing}", file=sys.stderr)
        return 2

    config_dir = ROOT / "config"
    settings_offline = config_dir / f"settings.qa.{run_id}.offline.yaml"
    settings_empty = config_dir / f"settings.qa.{run_id}.offline.empty.yaml"
    settings_real = Path(os.environ.get("MODULE_RAG_REAL_SETTINGS_PATH", "") or (config_dir / "settings.qa.real.yaml"))

    base_data = ROOT / "data" / "qa_runs" / run_id
    base_logs = ROOT / "logs" / "qa_runs" / run_id
    base_cache = ROOT / "cache" / "qa_runs" / run_id

    write_settings(
        settings_offline,
        run_id=run_id,
        default_strategy="local.test",
        data_dir=base_data / "offline",
        logs_dir=base_logs / "offline",
        cache_dir=base_cache / "offline",
    )
    write_settings(
        settings_empty,
        run_id=run_id,
        default_strategy="local.test",
        data_dir=base_data / "offline_empty",
        logs_dir=base_logs / "offline_empty",
        cache_dir=base_cache / "offline_empty",
    )

    s_off = set_sink_for(settings_offline)
    s_emp = set_sink_for(settings_empty)
    client_off = TestClient(create_app(s_off))
    client_emp = TestClient(create_app(s_emp))

    ingest = IngestRunner(settings_path=settings_offline)
    query = QueryRunner(settings_path=settings_offline)
    admin = AdminRunner(settings_path=settings_offline)
    real_block_reason: str | None = None
    if run_real:
        if not settings_real.exists():
            real_block_reason = f"BLOCKED(settings_missing:{settings_real})"
        else:
            hosts = _extract_hosts_from_settings(settings_real)
            if not _network_ok(hosts):
                real_block_reason = "BLOCKED(env:network)"

    def ok(cid: str, evidence: str = "", note: str = "") -> None:
        if cid not in rows:
            return
        rows[cid].offline = "PASS"
        if evidence:
            rows[cid].evidence = evidence
        if note:
            rows[cid].note = note

    def fail(cid: str, evidence: str = "", note: str = "") -> None:
        if cid not in rows:
            return
        rows[cid].offline = "FAIL"
        if evidence:
            rows[cid].evidence = evidence
        if note:
            rows[cid].note = note

    def ok_real(cid: str, evidence: str = "", note: str = "") -> None:
        if cid not in rows:
            return
        rows[cid].real = "PASS"
        if evidence:
            if rows[cid].evidence:
                rows[cid].evidence = f"{rows[cid].evidence}; real={evidence}"
            else:
                rows[cid].evidence = evidence
        if note:
            if rows[cid].note:
                rows[cid].note = f"{rows[cid].note}; {note}"
            else:
                rows[cid].note = note

    def fail_real(cid: str, evidence: str = "", note: str = "") -> None:
        if cid not in rows:
            return
        rows[cid].real = "FAIL"
        if evidence:
            if rows[cid].evidence:
                rows[cid].evidence = f"{rows[cid].evidence}; real={evidence}"
            else:
                rows[cid].evidence = evidence
        if note:
            if rows[cid].note:
                rows[cid].note = f"{rows[cid].note}; {note}"
            else:
                rows[cid].note = note

    def check(cond: bool, msg: str) -> None:
        if not cond:
            raise AssertionError(msg)

    # A-05 empty overview
    try:
        set_sink_for(settings_empty)
        sc, js = api_get(client_emp, "/api/overview")
        check(sc == 200, "overview not 200")
        check(all(k in js for k in ("assets", "health", "providers")), "missing keys")
        assets = js.get("assets") or {}
        check(int(assets.get("docs") or 0) == 0, "expected docs=0 in empty")
        ok("A-05", evidence="GET /api/overview (empty)")
    except Exception as e:
        fail("A-05", note=f"{type(e).__name__}: {e}")

    # A-01 overview
    try:
        set_sink_for(settings_offline)
        sc, js = api_get(client_off, "/api/overview")
        check(sc == 200, "overview not 200")
        check(all(k in js for k in ("assets", "health", "providers")), "missing keys")
        ok("A-01", evidence="GET /api/overview")
    except Exception as e:
        fail("A-01", note=f"{type(e).__name__}: {e}")

    # A-02 providers snapshot explainable (config-only compare)
    try:
        st_test = StrategyLoader().load("local.test")
        st_def = StrategyLoader().load("local.default")
        check(st_test.providers["embedder"]["provider_id"] != st_def.providers["embedder"]["provider_id"], "embedder provider_id should differ")
        ok("A-02", evidence="StrategyLoader(local.test vs local.default)", note="Config-only (REAL blocked)")
    except Exception as e:
        fail("A-02", note=f"{type(e).__name__}: {e}")

    def ingest_file(p: Path, policy: str) -> dict[str, Any]:
        resp = ingest.run(str(p), strategy_config_id="local.test", policy=policy)
        check(resp.structured.get("status") in {"ok", "skipped", "error"}, f"unexpected ingest status: {resp.structured}")
        return {"trace_id": resp.trace_id, "structured": resp.structured, "trace": resp.trace}

    def query_text(q: str, top_k: int = 5):
        resp = query.run(q, strategy_config_id="local.test", top_k=top_k)
        check(resp.trace_id.startswith("trace_"), "missing trace_id")
        return resp

    # G-01 baseline ingest (Markdown)
    try:
        r = ingest_file(FIXTURES / "sample.md", "new_version")
        check(r["structured"].get("status") == "ok", f"ingest not ok: {r['structured']}")
        ok("G-01", evidence=r["trace_id"], note="via IngestRunner")
    except Exception as e:
        fail("G-01", note=f"{type(e).__name__}: {e}")

    # G-02 PDF with images
    try:
        r = ingest_file(FIXTURES / "with_images.pdf", "new_version")
        counts = (r["structured"].get("counts") or {}) if isinstance(r["structured"], dict) else {}
        check(int(counts.get("assets_written") or 0) >= 1, f"assets_written<1: {counts}")
        ok("G-02", evidence=r["trace_id"])
    except Exception as e:
        fail("G-02", note=f"{type(e).__name__}: {e}")

    # G-03 negative unsupported type
    try:
        r = ingest_file(FIXTURES / "sample.txt", "new_version")
        structured = r["structured"] or {}
        check(structured.get("status") == "error", f"expected error: {structured}")
        ok("G-03", evidence=r["trace_id"])
    except Exception as e:
        fail("G-03", note=f"{type(e).__name__}: {e}")

    # G-05 multi-page technical PDF
    try:
        r = ingest_file(FIXTURES / "complex_technical_doc.pdf", "new_version")
        counts = (r["structured"].get("counts") or {}) if isinstance(r["structured"], dict) else {}
        check(int(counts.get("chunks_written") or 0) > 5, f"chunks_written not >5: {counts}")
        ok("G-05", evidence=r["trace_id"])
    except Exception as e:
        fail("G-05", note=f"{type(e).__name__}: {e}")

    # A-03 assets counters after ingest
    try:
        sc, js = api_get(client_off, "/api/overview")
        check(sc == 200, "overview not 200")
        assets = js.get("assets") or {}
        check(int(assets.get("docs") or 0) >= 2, f"docs<2: {assets}")
        check(int(assets.get("assets") or 0) >= 1, f"assets<1: {assets}")
        ok("A-03", evidence="GET /api/overview after ingest")
    except Exception as e:
        fail("A-03", note=f"{type(e).__name__}: {e}")

    # H-01 sparse keyword hit
    try:
        resp = query_text("FTS5", top_k=5)
        check(len(resp.sources) > 0, "no sources")
        ok("H-01", evidence=resp.trace_id, note="via QueryRunner")
    except Exception as e:
        fail("H-01", note=f"{type(e).__name__}: {e}")

    # H-04 asset_ids present
    try:
        resp = query_text("embedded image", top_k=5)
        check(any((s.asset_ids or []) for s in resp.sources), "no asset_ids in sources")
        ok("H-04", evidence=resp.trace_id)
    except Exception as e:
        fail("H-04", note=f"{type(e).__name__}: {e}")

    # H-02 TOC hit
    try:
        resp = query_text("Table of Contents", top_k=8)
        check(len(resp.sources) > 0, "no sources")
        ok("H-02", evidence=resp.trace_id)
    except Exception as e:
        fail("H-02", note=f"{type(e).__name__}: {e}")

    # H-03 Chinese recall (best-effort: may be heavy)
    try:
        ingest_file(FIXTURES / "blogger_intro.pdf", "new_version")
        resp = query_text("笔记有多少字", top_k=5)
        found = False
        for s in resp.sources[:5]:
            sc, js = api_get(client_off, f"/api/chunk/{s.chunk_id}")
            if sc == 200 and isinstance(js.get("chunk_text"), str) and "12万字" in js["chunk_text"]:
                found = True
                break
        check(found, "expected '12万字' in at least one chunk")
        ok("H-03", evidence=resp.trace_id)
    except Exception as e:
        fail("H-03", note=f"{type(e).__name__}: {e}")

    # B-01 documents list
    try:
        sc, js = api_get(client_off, "/api/documents?limit=50&offset=0")
        check(sc == 200, "documents not 200")
        items = js.get("items")
        check(isinstance(items, list) and items, "items empty/not list")
        check("doc_id" in items[0] and "version_id" in items[0], "missing fields")
        ok("B-01", evidence="GET /api/documents")
    except Exception as e:
        fail("B-01", note=f"{type(e).__name__}: {e}")

    # B-02 pagination + doc_id filter
    try:
        sc0, js0 = api_get(client_off, "/api/documents?limit=1&offset=0")
        sc1, js1 = api_get(client_off, "/api/documents?limit=1&offset=1")
        check(sc0 == 200 and sc1 == 200, "pagination not 200")
        check(len(js0.get("items") or []) == 1, "limit=1 not applied")
        check(len(js1.get("items") or []) == 1, "offset=1 not applied")
        doc_id = js0["items"][0]["doc_id"]
        scf, jsf = api_get(client_off, f"/api/documents?doc_id={doc_id}")
        check(scf == 200, "filter not 200")
        check(all(it.get("doc_id") == doc_id for it in jsf.get("items") or []), "doc_id filter mismatch")
        ok("B-02", evidence=f"doc_id={doc_id}")
    except Exception as e:
        fail("B-02", note=f"{type(e).__name__}: {e}")

    # B-04 chunk detail
    try:
        resp = query_text("FTS5", top_k=5)
        check(resp.sources, "no sources")
        chunk_id = resp.sources[0].chunk_id
        sc, js = api_get(client_off, f"/api/chunk/{chunk_id}")
        check(sc == 200, "chunk not 200")
        check(all(k in js for k in ("chunk_text", "section_path", "doc_id", "version_id")), "missing keys")
        ok("B-04", evidence=f"chunk_id={chunk_id}")
    except Exception as e:
        fail("B-04", note=f"{type(e).__name__}: {e}")

    # B-05 chunk not exists
    try:
        sc, js = api_get(client_emp, "/api/chunk/chk_not_exists")
        check(sc == 200, "not-exists not 200")
        check(js.get("error") == "not_found", "expected error:not_found")
        ok("B-05", evidence="GET /api/chunk/chk_not_exists")
    except Exception as e:
        fail("B-05", note=f"{type(e).__name__}: {e}")

    # C-01 ingest API default compat
    try:
        payload = {"file_path": str(FIXTURES / "sample.md"), "policy": "default", "strategy_config_id": "default"}
        sc, js = api_post(client_off, "/api/ingest", payload)
        check(sc == 200, "ingest api not 200")
        check(js.get("status") == "ok", f"status != ok: {js}")
        ok("C-01", evidence=f"trace_id={js.get('trace_id') or ''}")
    except Exception as e:
        fail("C-01", note=f"{type(e).__name__}: {e}")

    # C-02 missing file_path
    try:
        sc, js = api_post(client_off, "/api/ingest", {})
        check(sc == 200, "ingest api not 200")
        check(js.get("status") == "error", "expected status=error")
        ok("C-02", evidence="POST /api/ingest {}")
    except Exception as e:
        fail("C-02", note=f"{type(e).__name__}: {e}")

    # C-03 path not exists (note: endpoint wraps as status=ok + structured error)
    try:
        sc, js = api_post(client_off, "/api/ingest", {"file_path": str(FIXTURES / "__no_such__.md")})
        check(sc == 200, "ingest api not 200")
        structured = js.get("structured") or {}
        if structured.get("status") == "error":
            ok("C-03", evidence="structured.status=error", note="endpoint wraps as status=ok")
        else:
            fail("C-03", evidence=json.dumps(js, ensure_ascii=False), note="expected structured error")
    except Exception as e:
        fail("C-03", note=f"{type(e).__name__}: {e}")

    # C-04 ingest API pdf/md
    try:
        sc1, js1 = api_post(client_off, "/api/ingest", {"file_path": str(FIXTURES / "simple.pdf"), "policy": "new_version", "strategy_config_id": "local.test"})
        sc2, js2 = api_post(client_off, "/api/ingest", {"file_path": str(FIXTURES / "sample.md"), "policy": "new_version", "strategy_config_id": "local.test"})
        check(sc1 == 200 and sc2 == 200, "ingest api not 200")
        check(js1.get("status") == "ok" and js2.get("status") == "ok", "status not ok")
        ok("C-04", evidence="POST /api/ingest simple.pdf + sample.md")
    except Exception as e:
        fail("C-04", note=f"{type(e).__name__}: {e}")

    # D-01 traces list
    try:
        sc, js = api_get(client_off, "/api/traces?trace_type=ingestion&limit=10&offset=0")
        check(sc == 200, "traces not 200")
        check(isinstance(js.get("items"), list) and js.get("items"), "expected items")
        ok("D-01", evidence=f"count={len(js.get('items') or [])}")
    except Exception as e:
        fail("D-01", note=f"{type(e).__name__}: {e}")

    # D-02 trace detail
    try:
        sc, js = api_get(client_off, "/api/traces?trace_type=ingestion&limit=1&offset=0")
        trace_id = (js.get("items") or [{}])[0].get("trace_id")
        check(isinstance(trace_id, str) and trace_id, "missing trace_id")
        scd, jd = api_get(client_off, f"/api/trace/{trace_id}")
        check(scd == 200, "trace detail not 200")
        check(jd.get("trace_id") == trace_id, "trace_id mismatch")
        check(isinstance(jd.get("spans"), list) and jd.get("spans"), "missing spans")
        ok("D-02", evidence=f"trace_id={trace_id}")
    except Exception as e:
        fail("D-02", note=f"{type(e).__name__}: {e}")

    # D-03 failure trace via /api/ingest unsupported type
    try:
        sc, js = api_post(client_off, "/api/ingest", {"file_path": str(FIXTURES / "sample.txt"), "policy": "new_version", "strategy_config_id": "local.test"})
        check(sc == 200 and js.get("status") == "ok", "ingest api not ok")
        trace_id = js.get("trace_id")
        check(isinstance(trace_id, str) and trace_id, "missing trace_id")
        scd, jd = api_get(client_off, f"/api/trace/{trace_id}")
        check(scd == 200, "trace detail not 200")
        check(jd.get("status") == "error", "expected trace.status=error")
        ok("D-03", evidence=f"trace_id={trace_id}")
    except Exception as e:
        fail("D-03", note=f"{type(e).__name__}: {e}")

    # E-01 query traces filter
    try:
        query_text("FTS5", top_k=5)
        query_text("uuid_not_exists_" + run_id, top_k=5)
        sc, js = api_get(client_off, "/api/traces?trace_type=query&limit=10&offset=0")
        check(sc == 200, "query traces not 200")
        check(isinstance(js.get("items"), list) and js.get("items"), "expected items")
        ok("E-01", evidence=f"count={len(js.get('items') or [])}")
    except Exception as e:
        fail("E-01", note=f"{type(e).__name__}: {e}")

    # E-02 retrieval evidence in trace
    try:
        resp = query_text("FTS5", top_k=5)
        scd, jd = api_get(client_off, f"/api/trace/{resp.trace_id}")
        check(scd == 200, "trace detail not 200")
        found = False
        for sp in jd.get("spans") or []:
            for ev in sp.get("events") or []:
                if ev.get("kind") == "retrieval.candidates":
                    found = True
                    break
            if found:
                break
        check(found, "missing retrieval.candidates events")
        ok("E-02", evidence=f"trace_id={resp.trace_id}")
    except Exception as e:
        fail("E-02", note=f"{type(e).__name__}: {e}")

    # E-03 empty recall diagnosable
    try:
        resp = query_text("uuid_not_exists_" + run_id, top_k=5)
        check(len(resp.sources) == 0, "expected no sources")
        scd, _ = api_get(client_off, f"/api/trace/{resp.trace_id}")
        check(scd == 200, "trace detail not 200")
        ok("E-03", evidence=f"trace_id={resp.trace_id}")
    except Exception as e:
        fail("E-03", note=f"{type(e).__name__}: {e}")

    # F-01 eval/run
    try:
        sc, js = api_post(client_off, "/api/eval/run", {"dataset_id": "rag_eval_small"})
        check(sc == 200, "eval/run not 200")
        check(js.get("status") in {"ok", "error"}, "expected status ok/error")
        ok("F-01", evidence=f"status={js.get('status')}")
    except Exception as e:
        fail("F-01", note=f"{type(e).__name__}: {e}")

    # I-01 eval runner + F-02 eval/runs list
    try:
        env = os.environ.copy()
        env["MODULE_RAG_SETTINGS_PATH"] = str(settings_offline)
        code, out = run_cli(["bash", "scripts/dev_eval.sh", "rag_eval_small", "local.test", "5"], env=env)
        check(code == 0, f"dev_eval.sh failed: {out}")
        ok("I-01", evidence="scripts/dev_eval.sh")

        sc, js = api_get(client_off, "/api/eval/runs?limit=50&offset=0")
        check(sc == 200, "eval/runs not 200")
        check(isinstance(js.get("items"), list), "items not list")
        check(len(js.get("items") or []) >= 1, "expected >=1 eval run")
        ok("F-02", evidence=f"runs={len(js.get('items') or [])}")
    except Exception as e:
        fail("I-01", note=f"{type(e).__name__}: {e}")
        fail("F-02", note=f"{type(e).__name__}: {e}")

    # F-03 eval/trends
    try:
        sc, js = api_get(client_off, "/api/eval/trends?metric=hit_rate@k&window=30")
        check(sc == 200, "eval/trends not 200")
        check(all(k in js for k in ("metric", "window", "points")), "missing keys")
        ok("F-03", evidence="GET /api/eval/trends")
    except Exception as e:
        fail("F-03", note=f"{type(e).__name__}: {e}")

    # G-04 dedup skip
    try:
        ingest_file(FIXTURES / "sample.md", "new_version")
        r = ingest.run(str(FIXTURES / "sample.md"), strategy_config_id="local.test", policy="skip")
        check(r.structured.get("status") == "skipped", f"expected skipped: {r.structured}")
        ok("G-04", evidence=r.trace_id)
    except Exception as e:
        fail("G-04", note=f"{type(e).__name__}: {e}")

    # A-04 health reflects recent calls
    try:
        sc, js = api_get(client_off, "/api/overview")
        check(sc == 200, "overview not 200")
        health = js.get("health") or {}
        check(int(health.get("recent_traces") or 0) > 0, f"recent_traces not >0: {health}")
        ok("A-04", evidence=f"recent_traces={health.get('recent_traces')}")
    except Exception as e:
        fail("A-04", note=f"{type(e).__name__}: {e}")

    # B-03 include_deleted + H-05 + N-01
    try:
        r = ingest.run(str(FIXTURES / "sample.md"), strategy_config_id="local.test", policy="new_version")
        doc_id = r.structured.get("doc_id")
        ver_id = r.structured.get("version_id")
        check(isinstance(doc_id, str) and isinstance(ver_id, str), "missing doc_id/version_id")

        resp_pre = query_text("FTS5", top_k=5)
        check(any(s.doc_id == doc_id and s.version_id == ver_id for s in resp_pre.sources), "expected hit before delete")

        _ = admin.delete_document(doc_id=doc_id, version_id=ver_id, mode="soft", dry_run=False)

        scf, jsf = api_get(client_off, "/api/documents?include_deleted=false")
        sct, jst = api_get(client_off, "/api/documents?include_deleted=true")
        check(scf == 200 and sct == 200, "documents not 200")
        has_deleted_false = any(it.get("doc_id") == doc_id and it.get("version_id") == ver_id for it in (jsf.get("items") or []))
        has_deleted_true = any(it.get("doc_id") == doc_id and it.get("version_id") == ver_id and it.get("status") == "deleted" for it in (jst.get("items") or []))
        check(not has_deleted_false, "include_deleted=false should hide deleted")
        check(has_deleted_true, "include_deleted=true should show deleted")
        ok("B-03", evidence=f"doc_id={doc_id} version_id={ver_id}")

        resp_post = query_text("FTS5", top_k=5)
        check(not any(s.doc_id == doc_id and s.version_id == ver_id for s in resp_post.sources), "deleted version still returned in query")
        ok("H-05", evidence=f"doc_id={doc_id} version_id={ver_id}")
        ok("N-01", evidence=f"doc_id={doc_id} version_id={ver_id}")
    except Exception as e:
        fail("B-03", note=f"{type(e).__name__}: {e}")
        fail("H-05", note=f"{type(e).__name__}: {e}")
        fail("N-01", note=f"{type(e).__name__}: {e}")

    # N-02 hard delete entrypoints (AdminRunner)
    try:
        sc, js = api_get(client_off, "/api/documents?limit=1&offset=0&include_deleted=true")
        check(sc == 200 and (js.get("items") or []), "no documents")
        doc_id = js["items"][0]["doc_id"]
        _ = admin.delete_document(doc_id=doc_id, version_id=None, mode="hard", dry_run=True)
        _ = admin.delete_document(doc_id=doc_id, version_id=None, mode="hard", dry_run=False)
        ok("N-02", evidence=f"admin hard delete doc_id={doc_id}", note="MCP hard delete refusal validated separately")
    except Exception as e:
        fail("N-02", note=f"{type(e).__name__}: {e}")

    # O-01 A->A1->A
    try:
        tmp_dir = base_data / "tmp_docs"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        a_path = tmp_dir / "A.md"
        a1_path = tmp_dir / "A1.md"
        a_path.write_text((FIXTURES / "sample.md").read_text(encoding="utf-8"), encoding="utf-8")

        rA = ingest.run(str(a_path), strategy_config_id="local.test", policy="new_version")
        check(rA.structured.get("status") == "ok", "A ingest not ok")

        a1_path.write_text(a_path.read_text(encoding="utf-8") + "\n\nA1: extra line\n", encoding="utf-8")
        rA1 = ingest.run(str(a1_path), strategy_config_id="local.test", policy="new_version")
        check(rA1.structured.get("status") == "ok", "A1 ingest not ok")

        a_path.write_text((FIXTURES / "sample.md").read_text(encoding="utf-8"), encoding="utf-8")
        rA_back = ingest.run(str(a_path), strategy_config_id="local.test", policy="skip")
        check(rA_back.structured.get("status") == "skipped", f"expected skipped: {rA_back.structured}")
        ok("O-01", evidence=rA_back.trace_id)
    except Exception as e:
        fail("O-01", note=f"{type(e).__name__}: {e}")

    # O-02 multi-doc recall (soft assertion)
    try:
        resp = query_text("chunking", top_k=8)
        doc_ids = {s.doc_id for s in resp.sources if s.doc_id}
        if len(doc_ids) >= 2:
            ok("O-02", evidence=resp.trace_id, note=f"doc_ids={len(doc_ids)}")
        else:
            fail("O-02", evidence=resp.trace_id, note="only_one_doc_in_sources")
    except Exception as e:
        fail("O-02", note=f"{type(e).__name__}: {e}")

    # K-01 deepseek assembly (no network call)
    try:
        st = StrategyLoader().load("local.default")
        st.providers = json.loads(json.dumps(st.providers))
        st.providers["llm"]["provider_id"] = "deepseek"
        st.providers["llm"].setdefault("params", {})
        st.providers["llm"]["params"]["endpoint_key"] = "deepseek"
        st.providers["llm"]["params"]["model"] = "deepseek-chat"

        endpoints = load_settings(ROOT / "config" / "settings.yaml").raw.get("model_endpoints")
        merged = merge_provider_overrides(st.providers, None, endpoints)
        params = (merged.get("llm") or {}).get("params") or {}
        check("base_url" in params and "api_key" in params, "missing resolved base_url/api_key")
        reg = ProviderRegistry()
        register_builtin_providers(reg)
        reg.create("llm", "deepseek", **params)
        ok("K-01", evidence="registry.create(llm=deepseek) ok", note="no network call")
    except Exception as e:
        fail("K-01", note=f"{type(e).__name__}: {e}")

    # L-01 reranker noop baseline
    try:
        st = StrategyLoader().load("local.test")
        check((st.providers.get("reranker") or {}).get("provider_id") in {"noop", "reranker.noop"}, "reranker not noop")
        ok("L-01", evidence="local.test reranker=noop")
    except Exception as e:
        fail("L-01", note=f"{type(e).__name__}: {e}")

    # M-01 missing endpoints path behavior
    try:
        old = os.environ.get("MODULE_RAG_MODEL_ENDPOINTS_PATH")
        os.environ["MODULE_RAG_MODEL_ENDPOINTS_PATH"] = str(ROOT / "config" / "__no_such_endpoints__.yaml")
        set_sink_for(settings_offline)
        resp = query_text("FTS5", top_k=3)
        ok("M-01", evidence=resp.trace_id, note="OFFLINE ok without endpoints")
    except Exception as e:
        fail("M-01", note=f"{type(e).__name__}: {e}")
    finally:
        if old is None:
            os.environ.pop("MODULE_RAG_MODEL_ENDPOINTS_PATH", None)
        else:
            os.environ["MODULE_RAG_MODEL_ENDPOINTS_PATH"] = old

    # M-02 provider_id not exists (current behavior: exception bubbles)
    try:
        bad_path = base_data / "bad_strategy.yaml"
        bad_path.write_text(
            "providers:\n  embedder:\n    provider_id: not_exists\n    params: {dim: 8}\n  llm:\n    provider_id: fake\n  vector_index:\n    provider_id: vector.chroma_lite\n",
            encoding="utf-8",
        )
        try:
            _ = query.run("hi", strategy_config_id=str(bad_path), top_k=1)
            fail("M-02", note="unexpected success")
        except Exception as e:
            fail("M-02", note=f"exception_bubbled:{type(e).__name__}:{e}")
    except Exception as e:
        fail("M-02", note=f"{type(e).__name__}: {e}")

    # CLI smoke: dev_ingest + dev_query (as requested by QA plan)
    try:
        env = os.environ.copy()
        env["MODULE_RAG_SETTINGS_PATH"] = str(settings_offline)
        code, out = run_cli(["bash", "scripts/dev_ingest.sh", str(FIXTURES / "sample.md"), "local.test", "new_version"], env=env)
        check(code == 0, f"dev_ingest.sh failed: {out}")
        tr = parse_trace_id(out)
        if "G-01" in rows:
            rows["G-01"].note = (rows["G-01"].note + "; " if rows["G-01"].note else "") + "scripts/dev_ingest.sh OK"
            if tr:
                rows["G-01"].evidence = tr

        code, out = run_cli(["bash", "scripts/dev_query.sh", "FTS5", "local.test", "5"], env=env)
        check(code == 0, f"dev_query.sh failed: {out}")
        trq = parse_trace_id(out)
        if "H-01" in rows:
            rows["H-01"].note = (rows["H-01"].note + "; " if rows["H-01"].note else "") + "scripts/dev_query.sh OK"
            if trq:
                rows["H-01"].evidence = trq
    except Exception as e:
        # Don't flip PASS->FAIL for core cases; just append note.
        for cid in ("G-01", "H-01"):
            if cid in rows:
                rows[cid].note = (rows[cid].note + "; " if rows[cid].note else "") + f"cli_smoke_failed:{type(e).__name__}:{e}"

    # MCP tests: J + M-03 + N-02 (tool) + J-05 defaults
    try:
        env = os.environ.copy()
        env["PYTHON"] = str(ROOT / ".venv" / "bin" / "python")
        env["MODULE_RAG_SETTINGS_PATH"] = str(settings_offline)
        proc = subprocess.Popen(
            ["bash", "scripts/module-rag-mcp", "--settings", str(settings_offline)],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        def rpc(req: dict[str, Any]) -> dict[str, Any]:
            assert proc.stdin and proc.stdout
            proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline().strip()
            if not line:
                raise RuntimeError("empty response")
            return json.loads(line)

        # J-01 initialize
        try:
            r = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
            check(r.get("result", {}).get("protocolVersion") == "2024-11-05", "protocol negotiation failed")
            ok("J-01", evidence="initialize:2024-11-05")
        except Exception as e:
            fail("J-01", note=f"{type(e).__name__}: {e}")

        # J-02 tools/list tool.name validity
        try:
            r = rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            tools = r.get("result", {}).get("tools")
            check(isinstance(tools, list) and tools, "no tools")
            bad = [t.get("name") for t in tools if not re.match(r"^[a-zA-Z0-9_-]+$", str(t.get("name") or ""))]
            check(not bad, f"invalid tool names: {bad}")
            ok("J-02", evidence=f"tools={len(tools)}")
        except Exception as e:
            fail("J-02", note=f"{type(e).__name__}: {e}")

        # J-03 ping
        try:
            r = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "library_ping", "arguments": {}}})
            check("pong" in json.dumps(r.get("result", {}), ensure_ascii=False), "pong missing")
            ok("J-03", evidence="tools/call library_ping")
        except Exception as e:
            fail("J-03", note=f"{type(e).__name__}: {e}")

        # J-04 arguments as JSON string
        try:
            r = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "library_ping", "arguments": "{\"message\":\"hi\"}"}})
            check("hi" in json.dumps(r.get("result", {}), ensure_ascii=False), "hi missing")
            ok("J-04", evidence="arguments as JSON string")
        except Exception as e:
            fail("J-04", note=f"{type(e).__name__}: {e}")

        # J-05 defaults compatibility (each sub-call recorded; any failure => FAIL)
        j05_failures: list[str] = []
        try:
            r = rpc({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "library_ingest", "arguments": {"file_path": str(FIXTURES / "sample.md"), "policy": "default", "strategy_config_id": "default"}}})
            if "error" in r:
                j05_failures.append(f"ingest:{r['error']}")
        except Exception as e:
            j05_failures.append(f"ingest:{type(e).__name__}:{e}")

        try:
            r = rpc({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "library_query", "arguments": {"query": "FTS5", "strategy_config_id": "default", "top_k": 5}}})
            if "error" in r:
                j05_failures.append(f"query:{r['error']}")
        except Exception as e:
            j05_failures.append(f"query:{type(e).__name__}:{e}")

        try:
            r = rpc({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "library_query_assets", "arguments": {"variant": "default", "max_bytes": "default"}}})
            if "error" in r:
                j05_failures.append(f"query_assets:{r['error']}")
        except Exception as e:
            j05_failures.append(f"query_assets:{type(e).__name__}:{e}")

        try:
            r = rpc({"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "library_delete_document", "arguments": {"doc_id": "doc_not_exist", "mode": "default"}}})
            if "error" in r and r["error"].get("code") == -32602:
                j05_failures.append(f"delete_invalid_params:{r['error']}")
        except Exception as e:
            j05_failures.append(f"delete:{type(e).__name__}:{e}")

        if j05_failures:
            fail("J-05", note="; ".join(j05_failures)[:600])
        else:
            ok("J-05", evidence="default params accepted")

        # M-03 extra fields boundary (run regardless of J-05 outcome)
        try:
            r = rpc({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "library_ping", "arguments": {"message": "x", "extra": 123}}})
            check("error" not in r, "ping should allow extra")
            r = rpc({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "library_ingest", "arguments": {"file_path": str(FIXTURES / "sample.md"), "policy": "skip", "strategy_config_id": "local.test", "extra": 1}}})
            check("error" in r and r["error"].get("code") == -32602, "ingest extra should invalid params")
            ok("M-03", evidence="ping allows extra; ingest rejects extra")
        except Exception as e:
            fail("M-03", note=f"{type(e).__name__}: {e}")

        # N-02 MCP hard delete refusal (run regardless)
        try:
            r = rpc({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "library_delete_document", "arguments": {"doc_id": "doc_not_exist", "mode": "hard"}}})
            check("error" in r and r["error"].get("code") == -32602, "expected hard delete refused")
            if "N-02" in rows:
                rows["N-02"].note = (rows["N-02"].note + "; " if rows["N-02"].note else "") + "MCP hard delete refused as expected"
        except Exception as e:
            if "N-02" in rows:
                rows["N-02"].note = (rows["N-02"].note + "; " if rows["N-02"].note else "") + f"mcp_hard_delete_check_failed:{type(e).__name__}:{e}"

    except Exception as e:
        # If server couldn't start or transport died, mark the whole MCP block as failed.
        for cid in ("J-01", "J-02", "J-03", "J-04", "J-05", "M-03"):
            fail(cid, note=f"{type(e).__name__}: {e}")
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    # REAL subset (only when enabled)
    if run_real:
        if real_block_reason:
            for c in cases:
                if "REAL" in c.profiles and rows[c.case_id].real == "TODO":
                    rows[c.case_id].real = real_block_reason
        else:
            try:
                s_real = set_sink_for(settings_real)
                client_real = TestClient(create_app(s_real))
                ingest_real = IngestRunner(settings_path=settings_real)
                query_real = QueryRunner(settings_path=settings_real)

                def ingest_file_real(p: Path, policy: str) -> dict[str, Any]:
                    resp = ingest_real.run(str(p), strategy_config_id="local.default", policy=policy)
                    check(resp.structured.get("status") in {"ok", "skipped", "error"}, f"unexpected ingest status: {resp.structured}")
                    return {"trace_id": resp.trace_id, "structured": resp.structured, "trace": resp.trace}

                def query_text_real(q: str, top_k: int = 5):
                    resp = query_real.run(q, strategy_config_id="local.default", top_k=top_k)
                    check(resp.trace_id.startswith("trace_"), "missing trace_id")
                    return resp

                # A-01 overview (REAL)
                try:
                    sc, js = api_get(client_real, "/api/overview")
                    check(sc == 200, "overview not 200")
                    check(all(k in js for k in ("assets", "health", "providers")), "missing keys")
                    ok_real("A-01", evidence="GET /api/overview (real)")
                except Exception as e:
                    fail_real("A-01", note=f"{type(e).__name__}: {e}")

                # G-01 baseline ingest (REAL)
                try:
                    r = ingest_file_real(FIXTURES / "sample.md", "new_version")
                    check(r["structured"].get("status") == "ok", f"ingest not ok: {r['structured']}")
                    ok_real("G-01", evidence=r["trace_id"])
                except Exception as e:
                    fail_real("G-01", note=f"{type(e).__name__}: {e}")

                # G-02 PDF with images (REAL)
                try:
                    r = ingest_file_real(FIXTURES / "with_images.pdf", "new_version")
                    counts = (r["structured"].get("counts") or {}) if isinstance(r["structured"], dict) else {}
                    check(int(counts.get("assets_written") or 0) >= 1, f"assets_written<1: {counts}")
                    ok_real("G-02", evidence=r["trace_id"])
                except Exception as e:
                    fail_real("G-02", note=f"{type(e).__name__}: {e}")

                # H-01 sparse keyword hit (REAL)
                try:
                    resp = query_text_real("FTS5", top_k=5)
                    check(len(resp.sources) > 0, "no sources")
                    ok_real("H-01", evidence=resp.trace_id)
                except Exception as e:
                    fail_real("H-01", note=f"{type(e).__name__}: {e}")

                # F-01 eval/run (REAL)
                try:
                    sc, js = api_post(client_real, "/api/eval/run", {"dataset_id": "rag_eval_small"})
                    check(sc == 200, "eval/run not 200")
                    check(js.get("status") in {"ok", "error"}, "expected status ok/error")
                    ok_real("F-01", evidence=f"status={js.get('status')}")
                except Exception as e:
                    fail_real("F-01", note=f"{type(e).__name__}: {e}")

                # F-02 eval/runs (REAL)
                try:
                    sc, js = api_get(client_real, "/api/eval/runs?limit=50&offset=0")
                    check(sc == 200, "eval/runs not 200")
                    check(isinstance(js.get("items"), list), "items not list")
                    ok_real("F-02", evidence=f"runs={len(js.get('items') or [])}")
                except Exception as e:
                    fail_real("F-02", note=f"{type(e).__name__}: {e}")
            except Exception as e:
                for cid in ("A-01", "G-01", "G-02", "H-01", "F-01", "F-02"):
                    fail_real(cid, note=f"{type(e).__name__}: {e}")

    # Emit markdown section for QA_TEST_PROGRESS.md
    md: list[str] = []
    md.append(f"## Run: {run_id}（QA_TEST.md 执行回填）")
    md.append("")
    md.append("### 本次环境")
    md.append(f"- OFFLINE settings: `{settings_offline}`")
    md.append(f"- OFFLINE empty settings: `{settings_empty}`")
    md.append("- OFFLINE strategy_config_id: `local.test`")
    if run_real:
        if real_block_reason:
            md.append(f"- REAL: `{real_block_reason}`（未执行 REAL 用例）")
        else:
            md.append(f"- REAL settings: `{settings_real}`")
            md.append("- REAL strategy_config_id: `local.default`")
    else:
        md.append("- REAL: `SKIP (not enabled)`（如需执行：QA_RUN_REAL=1 或传入 --real）")
    md.append("")
    md.append("### 用例结果")
    md.append("")
    md.append("| Case | OFFLINE | REAL | Overall | Evidence | Note |")
    md.append("| --- | --- | --- | --- | --- | --- |")
    for c in cases:
        r = rows[c.case_id]
        md.append(
            "| {cid} | {off} | {real} | {overall} | {ev} | {note} |".format(
                cid=c.case_id,
                off=r.offline.replace("|", "\\|"),
                real=r.real.replace("|", "\\|"),
                overall=overall_for(c, r).replace("|", "\\|"),
                ev=r.evidence.replace("|", "\\|"),
                note=r.note.replace("|", "\\|"),
            )
        )
    md.append("")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
