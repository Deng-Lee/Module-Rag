from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from ..trace.envelope import EventRecord, SpanRecord, TraceEnvelope


def _event_from_dict(d: dict[str, Any]) -> EventRecord:
    return EventRecord(ts=float(d["ts"]), kind=str(d["kind"]), attrs=dict(d.get("attrs", {})))


def _span_from_dict(d: dict[str, Any]) -> SpanRecord:
    events = [_event_from_dict(e) for e in d.get("events", [])]
    return SpanRecord(
        span_id=str(d["span_id"]),
        name=str(d["name"]),
        parent_span_id=d.get("parent_span_id"),
        start_ts=float(d["start_ts"]),
        end_ts=float(d["end_ts"]) if d.get("end_ts") is not None else None,
        status=str(d.get("status", "ok")),
        attrs=dict(d.get("attrs", {})),
        events=events,
    )


def _envelope_from_dict(d: dict[str, Any]) -> TraceEnvelope:
    spans = [_span_from_dict(s) for s in d.get("spans", [])]
    events = [_event_from_dict(e) for e in d.get("events", [])]
    return TraceEnvelope(
        trace_id=str(d["trace_id"]),
        start_ts=float(d["start_ts"]),
        end_ts=float(d["end_ts"]),
        trace_type=str(d.get("trace_type", "unknown")),
        status=str(d.get("status", "ok")),
        strategy_config_id=str(d.get("strategy_config_id", "unknown")),
        spans=spans,
        events=events,
        aggregates=dict(d.get("aggregates", {})),
        providers=dict(d.get("providers", {})),
        schema_version=str(d.get("schema_version", "trace.v1")),
    )


class SqliteTraceReader:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def list_traces(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        trace_type: str | None = None,
        strategy_config_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.db_path.exists():
            return []
        where: list[str] = []
        params: list[Any] = []
        if trace_type:
            where.append("trace_type = ?")
            params.append(trace_type)
        if strategy_config_id:
            where.append("strategy_config_id = ?")
            params.append(strategy_config_id)
        if status:
            where.append("status = ?")
            params.append(status)

        sql = "SELECT trace_id, trace_type, status, start_ts, end_ts, strategy_config_id FROM traces"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY start_ts DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "trace_id": r[0],
                    "trace_type": r[1],
                    "status": r[2],
                    "start_ts": r[3],
                    "end_ts": r[4],
                    "strategy_config_id": r[5],
                }
            )
        return out

    def get_trace(self, trace_id: str) -> TraceEnvelope | None:
        if not self.db_path.exists():
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT envelope_json FROM traces WHERE trace_id = ? LIMIT 1",
                (trace_id,),
            ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        if not isinstance(data, dict):
            return None
        return _envelope_from_dict(data)

    def iter_traces(self) -> Iterable[TraceEnvelope]:
        if not self.db_path.exists():
            return iter(())
        with self._connect() as conn:
            rows = conn.execute("SELECT envelope_json FROM traces ORDER BY start_ts DESC").fetchall()
        for (raw,) in rows:
            data = json.loads(raw)
            if isinstance(data, dict):
                env = _envelope_from_dict(data)
                yield env
