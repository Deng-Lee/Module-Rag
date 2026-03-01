from __future__ import annotations

from pathlib import Path

from src.observability.obs import api as obs
from src.observability.sinks.sqlite import SqliteTraceSink
from src.observability.readers.sqlite_reader import SqliteTraceReader
from src.observability.trace.context import TraceContext


def _make_env(trace_id: str, db_path: Path) -> str:
    sink = SqliteTraceSink(db_path)
    ctx = TraceContext.new(trace_id, trace_type="query", strategy_config_id="scfg_test")
    ctx.providers_snapshot = {"embedder": {"provider_id": "embedder.fake"}}
    with TraceContext.activate(ctx):
        with obs.with_stage("retrieve_dense"):
            obs.event("retrieval.candidates", {"source": "dense", "count": 2})
        env = ctx.finish()
        sink.on_trace_end(env)
    return env.trace_id


def test_sqlite_trace_sink_and_reader(tmp_path: Path) -> None:
    db_path = tmp_path / "traces.sqlite"
    trace_id = _make_env("t-sql-1", db_path)
    assert trace_id == "t-sql-1"

    reader = SqliteTraceReader(db_path)
    items = reader.list_traces(limit=10, offset=0)
    assert len(items) == 1
    assert items[0]["trace_id"] == "t-sql-1"
    assert items[0]["trace_type"] == "query"

    env = reader.get_trace("t-sql-1")
    assert env is not None
    assert env.trace_id == "t-sql-1"
    assert env.providers.get("embedder", {}).get("provider_id") == "embedder.fake"
    assert env.aggregates["counters"]["retrieval.candidates.dense"] == 2
