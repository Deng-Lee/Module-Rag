from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..trace.envelope import TraceEnvelope


class SqliteTraceSink:
    """
    SQLite sink for trace envelopes (queryable for dashboard).
    Stores header fields as columns + full envelope JSON.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    trace_type TEXT,
                    status TEXT,
                    start_ts REAL,
                    end_ts REAL,
                    strategy_config_id TEXT,
                    providers_json TEXT,
                    aggregates_json TEXT,
                    envelope_json TEXT,
                    created_at REAL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_start_ts ON traces(start_ts DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_type ON traces(trace_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_strategy ON traces(strategy_config_id)")
            conn.commit()

    def write(self, envelope: TraceEnvelope) -> None:
        record = envelope.to_dict()
        providers_json = json.dumps(record.get("providers", {}), ensure_ascii=True)
        aggregates_json = json.dumps(record.get("aggregates", {}), ensure_ascii=True)
        envelope_json = json.dumps(record, ensure_ascii=True)
        created_at = float(record.get("end_ts") or record.get("start_ts") or 0.0)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO traces (
                    trace_id, trace_type, status, start_ts, end_ts,
                    strategy_config_id, providers_json, aggregates_json,
                    envelope_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("trace_id"),
                    record.get("trace_type"),
                    record.get("status"),
                    record.get("start_ts"),
                    record.get("end_ts"),
                    record.get("strategy_config_id"),
                    providers_json,
                    aggregates_json,
                    envelope_json,
                    created_at,
                ),
            )
            conn.commit()

    # --- ObsSink compatibility (optional) ---
    def on_event(self, record: dict[str, Any]) -> None:  # noqa: D401
        """No-op; SQLite sink persists full envelopes on trace end."""
        return

    def on_metric(self, record: dict[str, Any]) -> None:  # noqa: D401
        """No-op; SQLite sink persists full envelopes on trace end."""
        return

    def on_span_end(self, record: dict[str, Any]) -> None:  # noqa: D401
        """No-op; SQLite sink persists full envelopes on trace end."""
        return

    def on_trace_end(self, envelope: TraceEnvelope) -> None:
        self.write(envelope)
