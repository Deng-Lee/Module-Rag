from __future__ import annotations

from typing import Any

from fastapi import Request

from ...core.strategy import Settings
from ...ingestion.stages.storage.sqlite import SqliteStore
from ..readers.jsonl_reader import JsonlReader
from ..readers.sqlite_reader import SqliteTraceReader


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_trace_reader(settings: Settings) -> Any:
    sqlite_path = settings.paths.sqlite_dir / "traces.sqlite"
    if sqlite_path.exists():
        return SqliteTraceReader(sqlite_path)
    return JsonlReader(settings.paths.logs_dir / "traces.jsonl")


def get_sqlite_store(settings: Settings) -> SqliteStore:
    return SqliteStore(db_path=settings.paths.sqlite_dir / "app.sqlite")
