"""Ingestion stages (1 stage = 1 file)."""

from ..pipeline import DEFAULT_STAGE_ORDER, StageSpec
from .receive.dedup import DedupDecision, DedupStage
from .receive.loader import LoaderStage, detect_file_type
from .storage.fs import FsStore
from .storage.sqlite import SqliteStore

__all__ = [
    "StageSpec",
    "DEFAULT_STAGE_ORDER",
    "DedupStage",
    "DedupDecision",
    "FsStore",
    "SqliteStore",
    "LoaderStage",
    "detect_file_type",
]
